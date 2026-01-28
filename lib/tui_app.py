"""Textual TUI application for Azure Blob Cleanup."""

import asyncio
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TextArea,
)
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.message import Message

from lib.state import StateManager
from lib.storage_io import StorageIO
from lib.policy import PolicyManager
from lib.examples import ExamplesManager
from lib.triage_llm import TriageLLM

logger = logging.getLogger(__name__)


class HelpScreen(ModalScreen):
    """Help modal showing key bindings."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Label("🔑 Key Bindings", id="help-title")
            yield Static("""
j/k or ↓/↑   - Navigate items
Enter        - View details
K            - Mark as Keep
D            - Mark as Delete
H or Space   - Mark for Human Review
R            - Refresh queues
/            - Search/filter
F            - Toggle filters
B            - Batch action mode
A            - Add as few-shot example
E            - Edit policy (external editor)
G            - Run LLM triage now
T            - Toggle LLM worker
C            - View coverage stats
X            - Execute deletion (when 100% labeled)
?            - Show this help
Q            - Quit
            """, id="help-content")
            yield Button("Close", variant="primary", id="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle close button."""
        self.dismiss()


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog."""

    def __init__(self, message: str, confirm_text: str = ""):
        super().__init__()
        self.message = message
        self.confirm_text = confirm_text

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Label("⚠️ Confirmation Required", id="confirm-title")
            yield Static(self.message, id="confirm-message")
            if self.confirm_text:
                yield Label(f"Type '{self.confirm_text}' to confirm:", id="confirm-prompt")
                yield Input(placeholder=self.confirm_text, id="confirm-input")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Confirm", variant="error", id="confirm-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "confirm-btn":
            if self.confirm_text:
                input_widget = self.query_one("#confirm-input", Input)
                if input_widget.value == self.confirm_text:
                    self.dismiss(True)
                else:
                    self.notify("Confirmation text does not match", severity="error")
            else:
                self.dismiss(True)


class AddExampleScreen(ModalScreen[Optional[Dict]]):
    """Screen to add a few-shot example."""

    def __init__(self, blob_name: str):
        super().__init__()
        self.blob_name = blob_name

    def compose(self) -> ComposeResult:
        with Container(id="example-dialog"):
            yield Label(f"Add Example: {self.blob_name}", id="example-title")
            yield Label("Reason:", id="reason-label")
            yield TextArea(id="reason-input")
            yield Label("Optional cues (comma-separated):", id="cues-label")
            yield Input(placeholder="e.g., temporary, old, backup", id="cues-input")
            with Horizontal(id="example-buttons"):
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Add", variant="primary", id="add-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "add-btn":
            reason_area = self.query_one("#reason-input", TextArea)
            cues_input = self.query_one("#cues-input", Input)
            
            reason = reason_area.text.strip()
            if not reason:
                self.notify("Reason is required", severity="error")
                return
            
            cues = [c.strip() for c in cues_input.value.split(",") if c.strip()]
            
            self.dismiss({
                "reason": reason,
                "cues": cues,
            })


class BlobCleanupApp(App):
    """Main TUI application for Azure Blob Cleanup."""

    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        layout: horizontal;
        height: 100%;
    }
    
    #left-panel {
        width: 60%;
        border-right: solid $primary;
    }
    
    #right-panel {
        width: 40%;
        padding: 1;
    }
    
    #preview-content {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    
    #status-bar {
        dock: bottom;
        height: 3;
        background: $boost;
        padding: 1;
    }
    
    DataTable {
        height: 1fr;
    }
    
    #help-dialog, #confirm-dialog, #example-dialog {
        align: center middle;
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #help-title, #confirm-title, #example-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    #help-content {
        margin-bottom: 1;
    }
    
    #confirm-message {
        margin: 1;
    }
    
    #confirm-buttons, #example-buttons {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("?", "help", "Help"),
        ("k", "mark_keep", "Keep"),
        ("d", "mark_delete", "Delete"),
        ("h", "mark_review", "Review"),
        ("r", "refresh", "Refresh"),
        ("g", "run_triage", "Run Triage"),
        ("t", "toggle_worker", "Toggle Worker"),
        ("a", "add_example", "Add Example"),
        ("e", "edit_policy", "Edit Policy"),
        ("c", "show_coverage", "Coverage"),
        ("x", "execute_deletion", "Delete Blobs"),
    ]

    def __init__(
        self,
        storage_io: StorageIO,
        state_manager: StateManager,
        policy_manager: PolicyManager,
        examples_manager: ExamplesManager,
        triage_llm: Optional[TriageLLM] = None,
        container_name: str = "",
        prefix: str = "",
    ):
        super().__init__()
        self.storage_io = storage_io
        self.state = state_manager
        self.policy = policy_manager
        self.examples = examples_manager
        self.triage_llm = triage_llm
        self.container_name = container_name
        self.prefix = prefix
        
        self.current_queue = "review"
        self.worker_running = False
        self.worker_thread: Optional[threading.Thread] = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        
        with Container(id="main-container"):
            # Left panel: Queue table
            with Vertical(id="left-panel"):
                yield DataTable(id="queue-table")
            
            # Right panel: Preview
            with Vertical(id="right-panel"):
                yield Label("Preview", id="preview-title")
                yield VerticalScroll(
                    Static("Select an item to preview", id="preview-content"),
                    id="preview-scroll"
                )
        
        # Status bar
        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app."""
        table = self.query_one("#queue-table", DataTable)
        table.cursor_type = "row"
        
        # Add columns
        table.add_columns(
            "Decision", "Name", "Size", "Modified", "Type", "Source", "Reason"
        )
        
        # Load initial data
        self.refresh_table()
        self.update_status()

    def refresh_table(self) -> None:
        """Refresh the queue table."""
        table = self.query_one("#queue-table", DataTable)
        table.clear()
        
        # Load queue data
        df = self.state.read_queue(self.current_queue)
        
        for _, row in df.iterrows():
            decision = row.get("decision", "")
            icon = "✓" if decision == "keep" else "✗" if decision == "delete" else "?"
            
            name = row.get("name", "")[:50]
            size = self._format_size(row.get("size", 0))
            modified = row.get("decided_at", "")[:10] if "decided_at" in row else ""
            content_type = row.get("content_type", "")[:20] if "content_type" in row else ""
            source = row.get("source", "")
            reason = row.get("reason", "")[:40]
            
            table.add_row(
                icon,
                name,
                size,
                modified,
                content_type,
                source,
                reason,
                key=row.get("url", ""),
            )

    def _format_size(self, size) -> str:
        """Format file size."""
        try:
            size = int(size)
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.1f} GB"
        except:
            return "Unknown"

    def update_status(self) -> None:
        """Update status bar."""
        stats = self.state.get_coverage_stats()
        status_text = (
            f"Total: {stats['total']} | "
            f"Labeled: {stats['labeled']} ({stats['coverage']:.1%}) | "
            f"Review: {stats['to_review']} | "
            f"Delete: {stats['to_delete']} | "
            f"Keep: {stats['to_keep']} | "
            f"Worker: {'ON' if self.worker_running else 'OFF'}"
        )
        status = self.query_one("#status-bar", Static)
        status.update(status_text)

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        table = self.query_one("#queue-table", DataTable)
        row_key = event.row_key.value
        
        # Find the blob in the manifest
        manifest = self.state.read_manifest()
        if not manifest.empty and row_key in manifest["url"].values:
            blob = manifest[manifest["url"] == row_key].iloc[0]
            self.show_preview(blob)

    def show_preview(self, blob) -> None:
        """Show blob preview in right panel."""
        preview_content = self.query_one("#preview-content", Static)
        
        lines = [
            f"Container: {blob.get('container', 'N/A')}",
            f"Name: {blob.get('name', 'N/A')}",
            f"URL: {blob.get('url', 'N/A')}",
            f"Size: {self._format_size(blob.get('size', 0))}",
            f"Modified: {blob.get('last_modified', 'N/A')}",
            f"Type: {blob.get('content_type', 'N/A')}",
            "",
            "─" * 40,
            "Preview:",
            "",
            blob.get("preview_text", "[No preview available]")[:2000],
        ]
        
        preview_content.update("\n".join(lines))

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_mark_keep(self) -> None:
        """Mark selected item as keep."""
        self._mark_selected("keep")

    def action_mark_delete(self) -> None:
        """Mark selected item as delete."""
        self._mark_selected("delete")

    def action_mark_review(self) -> None:
        """Mark selected item for review."""
        self._mark_selected("review")

    def _mark_selected(self, target_queue: str) -> None:
        """Mark the currently selected item."""
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_row < 0:
            self.notify("No item selected", severity="warning")
            return
        
        row_key = table.get_row_at(table.cursor_row)[0]
        if not row_key:
            return
        
        # Move between queues
        self.state.move_between_queues(
            url=str(row_key),
            from_queue=self.current_queue,
            to_queue=target_queue,
            reason=f"Marked by user",
            source="human",
        )
        
        self.refresh_table()
        self.update_status()
        self.notify(f"Marked as {target_queue}", severity="information")

    def action_refresh(self) -> None:
        """Refresh the queue table."""
        self.refresh_table()
        self.update_status()
        self.notify("Refreshed", severity="information")

    def action_run_triage(self) -> None:
        """Manually trigger LLM triage."""
        if not self.triage_llm:
            self.notify("LLM not configured", severity="warning")
            return
        
        self.notify("Running LLM triage...", severity="information")
        self.run_triage_batch()

    def action_toggle_worker(self) -> None:
        """Toggle background LLM worker."""
        if self.worker_running:
            self.worker_running = False
            self.notify("Worker stopped", severity="information")
        else:
            self.worker_running = True
            self.start_background_worker()
            self.notify("Worker started", severity="information")
        self.update_status()

    def action_add_example(self) -> None:
        """Add selected item as few-shot example."""
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_row < 0:
            self.notify("No item selected", severity="warning")
            return
        
        row_key = table.get_row_at(table.cursor_row)[0]
        if not row_key:
            return
        
        # Get blob
        manifest = self.state.read_manifest()
        if manifest.empty or str(row_key) not in manifest["url"].values:
            self.notify("Blob not found in manifest", severity="error")
            return
        
        blob = manifest[manifest["url"] == str(row_key)].iloc[0]
        
        def handle_example(result: Optional[Dict]) -> None:
            if result:
                # Get decision from current queue
                queue_df = self.state.read_queue(self.current_queue)
                if not queue_df.empty and str(row_key) in queue_df["url"].values:
                    decision = queue_df[queue_df["url"] == str(row_key)].iloc[0].get("decision", "review")
                    label = "keep" if decision == "keep" else "delete" if decision == "delete" else None
                    
                    if label:
                        example = {
                            "label": label,
                            "reason": result["reason"],
                            "excerpt": blob.get("preview_text", "")[:1000],
                            "cues": result.get("cues", []),
                            "path_hint": blob.get("name", ""),
                            "content_type": blob.get("content_type", ""),
                            "reviewer": os.environ.get("USER", "unknown"),
                        }
                        self.examples.append_example(example)
                        self.notify("Example added", severity="information")
                    else:
                        self.notify("Item must be marked keep/delete first", severity="warning")
        
        self.push_screen(AddExampleScreen(blob.get("name", "unknown")), handle_example)

    def action_edit_policy(self) -> None:
        """Edit policy in external editor."""
        editor = os.environ.get("EDITOR", "nano")
        self.notify(f"Opening policy in {editor}...", severity="information")
        
        # Suspend app to run editor
        with self.suspend():
            success = self.policy.open_in_editor(editor)
        
        if success:
            self.notify("Policy updated", severity="information")
            self.update_status()
        else:
            self.notify("Editor failed", severity="error")

    def action_show_coverage(self) -> None:
        """Show coverage stats."""
        stats = self.state.get_coverage_stats()
        message = f"""
Coverage Statistics:
  Total blobs: {stats['total']}
  Labeled: {stats['labeled']} ({stats['coverage']:.1%})
  Remaining: {stats['remaining']}
  
Queue Breakdown:
  To Review: {stats['to_review']}
  To Delete: {stats['to_delete']}
  To Keep: {stats['to_keep']}
"""
        self.notify(message, severity="information", timeout=10)

    def action_execute_deletion(self) -> None:
        """Execute deletion after confirmation."""
        stats = self.state.get_coverage_stats()
        
        # Check if 100% labeled
        if stats['coverage'] < 1.0:
            self.notify(
                f"Cannot delete: only {stats['coverage']:.1%} labeled. All items must be labeled.",
                severity="error"
            )
            return
        
        # Get delete count
        delete_count = stats['to_delete']
        if delete_count == 0:
            self.notify("No items marked for deletion", severity="warning")
            return
        
        # Confirm deletion
        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                self.perform_deletion()
        
        self.push_screen(
            ConfirmDialog(
                f"You are about to DELETE {delete_count} blob(s).\nThis action cannot be undone.",
                confirm_text=f"DELETE {delete_count}"
            ),
            handle_confirm
        )

    def perform_deletion(self) -> None:
        """Perform the actual deletion."""
        self.notify("Starting deletion...", severity="warning")
        
        delete_df = self.state.read_queue("delete")
        total = len(delete_df)
        success_count = 0
        
        for idx, row in delete_df.iterrows():
            container = row.get("container", self.container_name)
            name = row.get("name", "")
            url = row.get("url", "")
            
            # Delete blob
            success = self.storage_io.delete_blob(container, name)
            
            # Log result
            self.state.append_audit_log({
                "url": url,
                "container": container,
                "name": name,
                "action": "delete_executed" if success else "delete_failed",
                "reason": "User confirmed deletion",
                "actor": "human",
                "at": datetime.utcnow().isoformat(),
                "policy_version": self.state.get_policy_version(),
                "examples_version": self.state.get_examples_version(),
            })
            
            if success:
                success_count += 1
        
        self.notify(
            f"Deletion complete: {success_count}/{total} succeeded",
            severity="information"
        )

    def run_triage_batch(self, batch_size: int = 20) -> None:
        """Run LLM triage on a batch of unlabeled items."""
        if not self.triage_llm:
            return
        
        # Get unlabeled URLs
        unlabeled = self.state.get_unlabeled_urls()
        if not unlabeled:
            logger.info("No unlabeled items")
            return
        
        # Get batch
        batch_urls = list(unlabeled)[:batch_size]
        
        # Get manifest data
        manifest = self.state.read_manifest()
        blobs_to_classify = []
        
        for url in batch_urls:
            if url in manifest["url"].values:
                blob = manifest[manifest["url"] == url].iloc[0].to_dict()
                blobs_to_classify.append(blob)
        
        if not blobs_to_classify:
            return
        
        # Get policy and examples
        policy = self.policy.summarize()
        examples = self.examples.format_for_prompt()
        
        # Classify
        results = self.triage_llm.batch_classify(policy, examples, blobs_to_classify)
        
        # Process results
        for result in results:
            label = result.get("label", "human_review")
            
            # Determine queue
            if label == "keep":
                queue = "keep"
            elif label == "delete":
                queue = "delete"
            else:
                queue = "review"
            
            # Add to queue
            item = {
                "url": result.get("url", ""),
                "container": result.get("container", ""),
                "name": result.get("name", ""),
                "reason": result.get("reason", ""),
                "policy_version": self.state.get_policy_version(),
                "examples_version": self.state.get_examples_version(),
            }
            self.state.add_to_queue(queue, [item], source="auto")
            
            # Save prediction
            self.state.write_predictions([{
                "url": result.get("url", ""),
                "policy_version": self.state.get_policy_version(),
                "examples_version": self.state.get_examples_version(),
                "label": label,
                "confidence": result.get("confidence", 0.0),
                "reason": result.get("reason", ""),
                "passes_self_consistency": result.get("passes_self_consistency", False),
                "created_at": datetime.utcnow().isoformat(),
            }])
        
        self.refresh_table()
        self.update_status()

    def start_background_worker(self) -> None:
        """Start background LLM worker thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            return
        
        def worker_loop():
            while self.worker_running:
                try:
                    self.run_triage_batch(batch_size=10)
                except Exception as e:
                    logger.error(f"Worker error: {e}")
                
                # Sleep between batches
                import time
                time.sleep(30)
        
        self.worker_thread = threading.Thread(target=worker_loop, daemon=True)
        self.worker_thread.start()

    def on_unmount(self) -> None:
        """Cleanup on exit."""
        self.worker_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
