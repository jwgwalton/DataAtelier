#!/usr/bin/env python3
"""
Azure Blob Cleanup TUI - Main Entry Point

A human-in-the-loop data cleansing tool for Azure Blob Storage that leverages LLMs for scale.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

from lib.storage_io import StorageIO
from lib.state import StateManager
from lib.policy import PolicyManager
from lib.examples import ExamplesManager
from lib.triage_llm import TriageLLM
from lib.tui_app import BlobCleanupApp

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="blob-cleanup",
    help="Azure Blob Storage cleanup assistant with human-in-the-loop workflow",
)


def validate_azure_credentials() -> tuple:
    """Validate and return Azure credentials."""
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")
    
    if not connection_string and not account_url:
        console.print("[red]Error: Azure Storage credentials not configured.[/red]")
        console.print("\nPlease set one of:")
        console.print("  - AZURE_STORAGE_CONNECTION_STRING")
        console.print("  - AZURE_STORAGE_ACCOUNT_URL (with optional AZURE_STORAGE_SAS_TOKEN)")
        sys.exit(1)
    
    return connection_string, account_url, sas_token


def inventory_blobs(
    storage_io: StorageIO,
    state: StateManager,
    container: str,
    prefix: Optional[str] = None,
    max_files: Optional[int] = None,
    preview_bytes: int = 4096,
) -> None:
    """Run blob inventory and create/update manifest."""
    console.print(f"\n[bold blue]📋 Starting inventory for container: {container}[/bold blue]")
    if prefix:
        console.print(f"   Prefix filter: {prefix}")
    if max_files:
        console.print(f"   Max files: {max_files}")
    
    try:
        # List blobs
        console.print("\n⏳ Listing blobs...")
        blobs = storage_io.list_blobs(container, prefix, max_files)
        console.print(f"✓ Found {len(blobs)} blobs")
        
        # Add previews for text files
        console.print("\n⏳ Generating previews...")
        for i, blob in enumerate(blobs):
            if (i + 1) % 10 == 0 or (i + 1) == len(blobs):
                console.print(f"   Progress: {i + 1}/{len(blobs)}")
            
            # Check if text content
            if storage_io.is_text_content(blob.get("content_type"), blob.get("name", "")):
                preview, is_text = storage_io.get_blob_preview(
                    container,
                    blob["name"],
                    max_bytes=preview_bytes,
                )
                blob["preview_text"] = preview if is_text else ""
            else:
                blob["preview_text"] = ""
        
        # Write manifest
        console.print("\n⏳ Writing manifest...")
        state.write_manifest(blobs)
        console.print(f"✓ Manifest updated: {state.manifest_path}")
        
    except Exception as e:
        console.print(f"[red]Error during inventory: {e}[/red]")
        sys.exit(1)


@app.command()
def run(
    container: str = typer.Option(
        None,
        "--container",
        "-c",
        envvar="AZURE_BLOB_CONTAINER",
        help="Azure Blob Storage container name",
    ),
    prefix: Optional[str] = typer.Option(
        None,
        "--prefix",
        "-p",
        envvar="AZURE_BLOB_PREFIX",
        help="Optional path prefix filter",
    ),
    max_files: Optional[int] = typer.Option(
        None,
        "--max-files",
        "-m",
        envvar="MAX_FILES",
        help="Maximum number of files to process (for testing)",
    ),
    preview_bytes: int = typer.Option(
        4096,
        "--preview-bytes",
        envvar="PREVIEW_MAX_BYTES",
        help="Maximum bytes to preview per file",
    ),
    work_dir: str = typer.Option(
        ".",
        "--work-dir",
        "-w",
        envvar="WORK_DIR",
        help="Working directory for state files",
    ),
    llm_model: str = typer.Option(
        "gpt-4",
        "--llm-model",
        envvar="OPENAI_MODEL",
        help="LLM model to use",
    ),
    llm_off: bool = typer.Option(
        False,
        "--llm-off",
        help="Disable LLM triage (manual mode only)",
    ),
    confidence_threshold: float = typer.Option(
        0.95,
        "--confidence",
        envvar="CERTAINTY_CONF_THRESHOLD",
        help="Confidence threshold for auto-accept",
    ),
    self_consistency_passes: int = typer.Option(
        3,
        "--self-consistency",
        envvar="SELF_CONSISTENCY_PASSES",
        help="Number of self-consistency passes",
    ),
    use_azure_openai: bool = typer.Option(
        False,
        "--azure-openai",
        help="Use Azure OpenAI instead of OpenAI",
    ),
    skip_inventory: bool = typer.Option(
        False,
        "--skip-inventory",
        help="Skip inventory step (use existing manifest)",
    ),
) -> None:
    """Run the Azure Blob Cleanup TUI application."""
    
    # Validate container
    if not container:
        console.print("[red]Error: --container is required[/red]")
        console.print("Usage: python azure_blob_cleanup_tui.py run --container CONTAINER_NAME")
        console.print("Or set AZURE_BLOB_CONTAINER environment variable")
        sys.exit(1)
    
    # Validate Azure credentials
    connection_string, account_url, sas_token = validate_azure_credentials()
    
    # Initialize components
    console.print("\n[bold blue]🚀 Initializing Azure Blob Cleanup Assistant[/bold blue]")
    
    # Storage I/O
    try:
        storage_io = StorageIO(
            connection_string=connection_string,
            account_url=account_url,
            sas_token=sas_token,
        )
        console.print("✓ Connected to Azure Storage")
    except Exception as e:
        console.print(f"[red]Error connecting to Azure Storage: {e}[/red]")
        sys.exit(1)
    
    # State manager
    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)
    state = StateManager(work_dir=work_dir)
    console.print(f"✓ Initialized state manager (work dir: {work_dir})")
    
    # Policy manager
    policy = PolicyManager(state.policy_path)
    console.print(f"✓ Loaded policy (version: {policy.get_version()})")
    
    # Examples manager
    examples = ExamplesManager(state.examples_path)
    example_counts = examples.count_by_label()
    console.print(f"✓ Loaded examples (keep: {example_counts['keep']}, delete: {example_counts['delete']})")
    
    # LLM triage
    triage_llm = None
    if not llm_off:
        try:
            triage_llm = TriageLLM(
                model=llm_model,
                confidence_threshold=confidence_threshold,
                self_consistency_passes=self_consistency_passes,
                use_azure=use_azure_openai,
            )
            console.print(f"✓ Initialized LLM triage (model: {llm_model})")
        except Exception as e:
            console.print(f"[yellow]Warning: LLM initialization failed: {e}[/yellow]")
            console.print("[yellow]Continuing in manual mode (LLM disabled)[/yellow]")
    else:
        console.print("ℹ️  LLM triage disabled (manual mode)")
    
    # Run inventory unless skipped
    if not skip_inventory:
        inventory_blobs(
            storage_io,
            state,
            container,
            prefix,
            max_files,
            preview_bytes,
        )
    else:
        console.print("\nℹ️  Skipping inventory (using existing manifest)")
        manifest = state.read_manifest()
        if manifest.empty:
            console.print("[red]Error: No existing manifest found. Remove --skip-inventory flag.[/red]")
            sys.exit(1)
        console.print(f"✓ Loaded manifest with {len(manifest)} blobs")
    
    # Display stats
    stats = state.get_coverage_stats()
    console.print("\n[bold]Current Status:[/bold]")
    console.print(f"  Total blobs: {stats['total']}")
    console.print(f"  Labeled: {stats['labeled']} ({stats['coverage']:.1%})")
    console.print(f"  To review: {stats['to_review']}")
    console.print(f"  To delete: {stats['to_delete']}")
    console.print(f"  To keep: {stats['to_keep']}")
    
    # Start TUI
    console.print("\n[bold green]🎨 Starting TUI application...[/bold green]")
    console.print("Press ? for help, Q to quit\n")
    
    tui_app = BlobCleanupApp(
        storage_io=storage_io,
        state_manager=state,
        policy_manager=policy,
        examples_manager=examples,
        triage_llm=triage_llm,
        container_name=container,
        prefix=prefix or "",
    )
    
    try:
        tui_app.run()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n\n[red]Error running TUI: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Final stats
    console.print("\n[bold blue]📊 Final Statistics[/bold blue]")
    stats = state.get_coverage_stats()
    console.print(f"  Total blobs: {stats['total']}")
    console.print(f"  Labeled: {stats['labeled']} ({stats['coverage']:.1%})")
    console.print(f"  To review: {stats['to_review']}")
    console.print(f"  To delete: {stats['to_delete']}")
    console.print(f"  To keep: {stats['to_keep']}")
    
    console.print("\n[bold green]✓ Session complete[/bold green]")


@app.command()
def archive(
    work_dir: str = typer.Option(
        ".",
        "--work-dir",
        "-w",
        help="Working directory with state files",
    ),
) -> None:
    """Archive all artifacts to a timestamped directory."""
    state = StateManager(work_dir=work_dir)
    archive_path = state.archive_artifacts()
    console.print(f"[green]✓ Artifacts archived to: {archive_path}[/green]")


@app.command()
def stats(
    work_dir: str = typer.Option(
        ".",
        "--work-dir",
        "-w",
        help="Working directory with state files",
    ),
) -> None:
    """Display current statistics."""
    state = StateManager(work_dir=work_dir)
    stats = state.get_coverage_stats()
    
    console.print("\n[bold]Coverage Statistics[/bold]")
    console.print(f"  Total blobs: {stats['total']}")
    console.print(f"  Labeled: {stats['labeled']} ({stats['coverage']:.1%})")
    console.print(f"  Remaining: {stats['remaining']}")
    console.print("\n[bold]Queue Breakdown[/bold]")
    console.print(f"  To Review: {stats['to_review']}")
    console.print(f"  To Delete: {stats['to_delete']}")
    console.print(f"  To Keep: {stats['to_keep']}")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
