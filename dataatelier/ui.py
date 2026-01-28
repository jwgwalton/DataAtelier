"""Jupyter UI components for DataAtelier blob cleanup.

This module provides interactive widgets for human review and progress display.
This is the ONLY module that can use ipywidgets and IPython.
"""

import json
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    import ipywidgets as widgets
    from IPython.display import display, HTML, clear_output
    IPYWIDGETS_AVAILABLE = True
except ImportError:
    IPYWIDGETS_AVAILABLE = False

from .config import Config
from .models import QueueEntry, AuditEntry
from .queue import load_queue, remove_from_queue, add_to_queue, get_statistics
from .audit import log_audit
from .policy import save_few_shot_example
from .models import FewShotExample


class ReviewUI:
    """Interactive widget-based UI for human review of blobs.
    
    Provides a user-friendly interface for reviewing blobs that were
    flagged for human review by the LLM triage system.
    """
    
    def __init__(self, config: Config):
        """Initialize ReviewUI.
        
        Args:
            config: Configuration object with file paths
            
        Raises:
            ImportError: If ipywidgets is not available
        """
        if not IPYWIDGETS_AVAILABLE:
            raise ImportError(
                "ipywidgets and IPython are required for ReviewUI. "
                "Install with: pip install ipywidgets ipython"
            )
        
        self.config = config
        self.current_item: Optional[dict] = None
        self.current_index = 0
        
        # Widgets
        self.output = widgets.Output()
        self.info_html = widgets.HTML()
        self.preview_text = widgets.Textarea(
            layout=widgets.Layout(width='100%', height='200px'),
            disabled=True
        )
        self.reason_input = widgets.Textarea(
            placeholder='Enter reason for your decision...',
            layout=widgets.Layout(width='100%', height='80px')
        )
        self.keep_button = widgets.Button(
            description='Keep',
            button_style='success',
            icon='check',
            layout=widgets.Layout(width='100px')
        )
        self.delete_button = widgets.Button(
            description='Delete',
            button_style='danger',
            icon='trash',
            layout=widgets.Layout(width='100px')
        )
        self.skip_button = widgets.Button(
            description='Skip',
            button_style='',
            icon='forward',
            layout=widgets.Layout(width='100px')
        )
        self.save_example_checkbox = widgets.Checkbox(
            value=False,
            description='Save as training example',
            indent=False
        )
        self.status_label = widgets.Label()
        
        # Button handlers
        self.keep_button.on_click(self._on_keep_clicked)
        self.delete_button.on_click(self._on_delete_clicked)
        self.skip_button.on_click(self._on_skip_clicked)
    
    def create_widget(self) -> widgets.VBox:
        """Create the review widget.
        
        Returns:
            VBox widget containing the full UI
        """
        # Header
        header = widgets.HTML(
            value='<h2>Blob Review Interface</h2>',
            layout=widgets.Layout(margin='10px 0')
        )
        
        # Info section
        info_box = widgets.VBox([
            widgets.HTML(value='<h3>Blob Information</h3>'),
            self.info_html
        ])
        
        # Preview section
        preview_box = widgets.VBox([
            widgets.HTML(value='<h3>Content Preview</h3>'),
            self.preview_text
        ])
        
        # Decision section
        decision_box = widgets.VBox([
            widgets.HTML(value='<h3>Your Decision</h3>'),
            self.reason_input,
            widgets.HBox([
                self.keep_button,
                self.delete_button,
                self.skip_button
            ], layout=widgets.Layout(margin='10px 0')),
            self.save_example_checkbox,
            self.status_label
        ])
        
        # Main layout
        main_widget = widgets.VBox([
            header,
            info_box,
            preview_box,
            decision_box,
            self.output
        ], layout=widgets.Layout(padding='20px'))
        
        return main_widget
    
    def load_next_item(self) -> bool:
        """Load the next item from the review queue.
        
        Returns:
            True if item was loaded, False if no more items
        """
        try:
            # Load review queue
            review_entries = load_queue(self.config.to_review_file)
            
            if not review_entries:
                self._show_completion_message()
                return False
            
            # Get first entry
            entry = review_entries[0]
            
            # Load manifest to get full blob info
            import pandas as pd
            manifest_path = Path(self.config.manifest_file)
            
            if manifest_path.exists():
                manifest_df = pd.read_csv(manifest_path)
                blob_row = manifest_df[manifest_df['name'] == entry.name]
                
                if not blob_row.empty:
                    row = blob_row.iloc[0]
                    self.current_item = {
                        'name': entry.name,
                        'url': entry.url,
                        'path': row.get('path', ''),
                        'size': int(row.get('size', 0)),
                        'content_type': row.get('content_type', ''),
                        'last_modified': row.get('last_modified', ''),
                        'preview': row.get('preview', ''),
                        'llm_decision': entry.decision,
                        'llm_reason': entry.reason,
                        'llm_confidence': entry.confidence
                    }
                else:
                    # Fallback to basic info
                    self.current_item = {
                        'name': entry.name,
                        'url': entry.url,
                        'preview': '',
                        'llm_decision': entry.decision,
                        'llm_reason': entry.reason,
                        'llm_confidence': entry.confidence
                    }
            else:
                # Fallback to basic info
                self.current_item = {
                    'name': entry.name,
                    'url': entry.url,
                    'preview': '',
                    'llm_decision': entry.decision,
                    'llm_reason': entry.reason,
                    'llm_confidence': entry.confidence
                }
            
            # Update UI
            self._update_display()
            self.current_index += 1
            
            return True
            
        except Exception as e:
            with self.output:
                print(f"Error loading next item: {e}")
            return False
    
    def _update_display(self):
        """Update the widget display with current item info."""
        if not self.current_item:
            return
        
        # Format info HTML
        info_html = f"""
        <table style='width: 100%; border-collapse: collapse;'>
            <tr><td style='padding: 5px;'><b>Name:</b></td><td style='padding: 5px;'>{self.current_item.get('name', 'N/A')}</td></tr>
            <tr><td style='padding: 5px;'><b>Path:</b></td><td style='padding: 5px;'>{self.current_item.get('path', 'N/A')}</td></tr>
            <tr><td style='padding: 5px;'><b>Size:</b></td><td style='padding: 5px;'>{self.current_item.get('size', 0)} bytes</td></tr>
            <tr><td style='padding: 5px;'><b>Type:</b></td><td style='padding: 5px;'>{self.current_item.get('content_type', 'N/A')}</td></tr>
            <tr><td style='padding: 5px;'><b>Modified:</b></td><td style='padding: 5px;'>{self.current_item.get('last_modified', 'N/A')}</td></tr>
            <tr><td style='padding: 5px;'><b>LLM Decision:</b></td><td style='padding: 5px;'>{self.current_item.get('llm_decision', 'N/A')}</td></tr>
            <tr><td style='padding: 5px;'><b>LLM Confidence:</b></td><td style='padding: 5px;'>{self.current_item.get('llm_confidence', 0):.2f}</td></tr>
            <tr><td style='padding: 5px;'><b>LLM Reason:</b></td><td style='padding: 5px;'>{self.current_item.get('llm_reason', 'N/A')}</td></tr>
        </table>
        """
        self.info_html.value = info_html
        
        # Update preview
        preview = self.current_item.get('preview', '')
        if len(preview) > 2000:
            preview = preview[:2000] + "\n... (truncated)"
        self.preview_text.value = preview
        
        # Clear reason input
        self.reason_input.value = ''
        self.save_example_checkbox.value = False
        
        # Update status
        stats = get_statistics(self.config)
        self.status_label.value = f"Review Queue: {stats.get('to_review', 0)} items remaining"
    
    def _show_completion_message(self):
        """Show completion message when review queue is empty."""
        self.info_html.value = "<h3 style='color: green;'>✓ All items reviewed!</h3>"
        self.preview_text.value = "No more items in the review queue."
        self.status_label.value = "Review complete"
        
        # Disable buttons
        self.keep_button.disabled = True
        self.delete_button.disabled = True
        self.skip_button.disabled = True
    
    def _on_keep_clicked(self, button):
        """Handle keep button click."""
        self._process_decision('keep')
    
    def _on_delete_clicked(self, button):
        """Handle delete button click."""
        self._process_decision('delete')
    
    def _on_skip_clicked(self, button):
        """Handle skip button click."""
        with self.output:
            clear_output()
            print("Skipped - item remains in review queue")
        
        # Load next item
        self.load_next_item()
    
    def _process_decision(self, decision: str):
        """Process a user decision (keep or delete).
        
        Args:
            decision: 'keep' or 'delete'
        """
        if not self.current_item:
            return
        
        reason = self.reason_input.value.strip()
        if not reason:
            with self.output:
                clear_output()
                print("❌ Please provide a reason for your decision")
            return
        
        try:
            # Remove from review queue
            remove_from_queue(self.config.to_review_file, self.current_item['name'])
            
            # Add to appropriate queue
            queue_file = self.config.to_keep_file if decision == 'keep' else self.config.to_delete_file
            
            entry = QueueEntry(
                url=self.current_item.get('url', ''),
                container=self.config.container_name,
                name=self.current_item['name'],
                decision=decision,
                reason=reason,
                source='human',
                decided_at=datetime.utcnow().isoformat(),
                policy_version='',
                examples_version='',
                confidence=1.0
            )
            
            add_to_queue(queue_file, entry)
            
            # Log audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.utcnow().isoformat(),
                blob_name=self.current_item['name'],
                action=f'human_{decision}',
                source='human',
                reason=reason,
                metadata=json.dumps({
                    'previous_llm_decision': self.current_item.get('llm_decision', ''),
                    'previous_llm_confidence': self.current_item.get('llm_confidence', 0)
                })
            )
            log_audit(self.config.audit_log_file, audit_entry)
            
            # Save as few-shot example if requested
            if self.save_example_checkbox.value:
                self._save_as_example(decision, reason)
            
            with self.output:
                clear_output()
                icon = '✓' if decision == 'keep' else '🗑'
                print(f"{icon} {decision.upper()}: {self.current_item['name']}")
                if self.save_example_checkbox.value:
                    print("  📝 Saved as training example")
            
            # Load next item
            self.load_next_item()
            
        except Exception as e:
            with self.output:
                clear_output()
                print(f"❌ Error processing decision: {e}")
    
    def _save_as_example(self, decision: str, reason: str):
        """Save current item as a few-shot learning example.
        
        Args:
            decision: 'keep' or 'delete'
            reason: User's reason for the decision
        """
        try:
            example = FewShotExample(
                label=decision,
                reason=reason,
                excerpt=self.current_item.get('preview', '')[:500],
                path_hint=self.current_item.get('path', ''),
                content_type=self.current_item.get('content_type', ''),
                date=datetime.utcnow().isoformat(),
                reviewer='human',
                cues=[]
            )
            
            save_few_shot_example(self.config.few_shot_file, example)
            
        except Exception as e:
            with self.output:
                print(f"Warning: Failed to save example: {e}")


class ProgressDisplay:
    """Widget for displaying cleanup progress statistics."""
    
    def __init__(self, config: Config):
        """Initialize ProgressDisplay.
        
        Args:
            config: Configuration object with file paths
            
        Raises:
            ImportError: If ipywidgets is not available
        """
        if not IPYWIDGETS_AVAILABLE:
            raise ImportError(
                "ipywidgets and IPython are required for ProgressDisplay. "
                "Install with: pip install ipywidgets ipython"
            )
        
        self.config = config
    
    def create_widget(self) -> widgets.HTML:
        """Create progress display widget.
        
        Returns:
            HTML widget showing statistics
        """
        stats = get_statistics(self.config)
        
        total = stats.get('total_blobs', 0)
        labeled = stats.get('labeled', 0)
        unlabeled = stats.get('unlabeled', 0)
        to_keep = stats.get('to_keep', 0)
        to_delete = stats.get('to_delete', 0)
        to_review = stats.get('to_review', 0)
        auto_labeled = stats.get('auto_labeled', 0)
        human_labeled = stats.get('human_labeled', 0)
        
        # Calculate percentages
        labeled_pct = (labeled / total * 100) if total > 0 else 0
        
        html_content = f"""
        <div style='font-family: sans-serif; padding: 20px; background: #f5f5f5; border-radius: 5px;'>
            <h2 style='margin-top: 0;'>Cleanup Progress</h2>
            
            <div style='margin: 20px 0;'>
                <div style='background: #fff; padding: 15px; border-radius: 5px; margin: 10px 0;'>
                    <h3 style='margin-top: 0;'>Overall Progress</h3>
                    <div style='background: #e0e0e0; height: 30px; border-radius: 15px; overflow: hidden;'>
                        <div style='background: linear-gradient(90deg, #4CAF50, #45a049); height: 100%; width: {labeled_pct:.1f}%; 
                                    display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;'>
                            {labeled_pct:.1f}%
                        </div>
                    </div>
                    <p style='margin: 10px 0 0 0;'>
                        <b>{labeled}</b> of <b>{total}</b> blobs labeled 
                        (<b>{unlabeled}</b> remaining)
                    </p>
                </div>
                
                <div style='background: #fff; padding: 15px; border-radius: 5px; margin: 10px 0;'>
                    <h3 style='margin-top: 0;'>Queue Status</h3>
                    <table style='width: 100%; border-collapse: collapse;'>
                        <tr>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd;'>
                                <span style='color: #4CAF50; font-size: 20px;'>✓</span> <b>To Keep:</b>
                            </td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right;'>
                                <b>{to_keep}</b>
                            </td>
                        </tr>
                        <tr>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd;'>
                                <span style='color: #f44336; font-size: 20px;'>🗑</span> <b>To Delete:</b>
                            </td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right;'>
                                <b>{to_delete}</b>
                            </td>
                        </tr>
                        <tr>
                            <td style='padding: 8px;'>
                                <span style='color: #FF9800; font-size: 20px;'>👤</span> <b>To Review:</b>
                            </td>
                            <td style='padding: 8px; text-align: right;'>
                                <b>{to_review}</b>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <div style='background: #fff; padding: 15px; border-radius: 5px; margin: 10px 0;'>
                    <h3 style='margin-top: 0;'>Decision Sources</h3>
                    <table style='width: 100%;'>
                        <tr>
                            <td style='padding: 5px;'>🤖 <b>Auto-labeled (LLM):</b></td>
                            <td style='padding: 5px; text-align: right;'><b>{auto_labeled}</b></td>
                        </tr>
                        <tr>
                            <td style='padding: 5px;'>👤 <b>Human-labeled:</b></td>
                            <td style='padding: 5px; text-align: right;'><b>{human_labeled}</b></td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
        """
        
        return widgets.HTML(value=html_content)


def create_progress_widget(config: Config) -> widgets.HTML:
    """Create a progress display widget.
    
    Convenience function for creating a progress widget.
    
    Args:
        config: Configuration object with file paths
        
    Returns:
        HTML widget showing statistics
        
    Raises:
        ImportError: If ipywidgets is not available
    """
    display = ProgressDisplay(config)
    return display.create_widget()
