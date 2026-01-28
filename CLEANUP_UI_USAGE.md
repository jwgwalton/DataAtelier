# Using cleanup.py and ui.py - Quick Start Guide

This guide shows how to use the new `cleanup.py` and `ui.py` modules for DataAtelier blob cleanup.

## Installation

```bash
pip install -r requirements.txt
```

## Basic Usage with cleanup.py (Programmatic)

The `cleanup.py` module provides a pure Python interface (no Jupyter required):

```python
from dataatelier import Config, BlobCleanup

# 1. Configure
config = Config(
    storage_connection_string="your_connection_string",
    container_name="your_container",
    llm_provider="openai",
    openai_api_key="your_api_key",
    confidence_threshold=0.95,
    self_consistency_runs=3,
    batch_size=20
)

# 2. Initialize cleanup orchestrator
cleanup = BlobCleanup(config)

# 3. Create manifest of all blobs
manifest_df = cleanup.create_manifest()
print(f"Found {len(manifest_df)} blobs")

# 4. Run LLM triage on a batch
stats = cleanup.run_triage_batch(batch_size=20)
print(f"Processed: {stats['processed']}")
print(f"To Keep: {stats['to_keep']}")
print(f"To Delete: {stats['to_delete']}")
print(f"To Review: {stats['to_review']}")

# 5. Check progress
progress = cleanup.show_progress()
print(f"Total: {progress['total_blobs']}")
print(f"Labeled: {progress['labeled']}")
print(f"Unlabeled: {progress['unlabeled']}")

# 6. Continue until all are labeled
while cleanup.get_unlabeled_count() > 0:
    stats = cleanup.run_triage_batch()
    print(f"Batch complete. {cleanup.get_unlabeled_count()} remaining")

# 7. Archive artifacts
archive_path = cleanup.archive_artifacts("./archives")
print(f"Artifacts archived to: {archive_path}")
```

## Interactive Review with ui.py (Jupyter Notebook)

The `ui.py` module provides ipywidgets-based UI for human review:

```python
from dataatelier import Config
from dataatelier.ui import ReviewUI, create_progress_widget
from IPython.display import display

# 1. Configure (same as above)
config = Config(
    storage_connection_string="your_connection_string",
    container_name="your_container",
    llm_provider="openai",
    openai_api_key="your_api_key"
)

# 2. Show progress widget
progress_widget = create_progress_widget(config)
display(progress_widget)

# 3. Create review UI
review_ui = ReviewUI(config)
review_widget = review_ui.create_widget()
display(review_widget)

# 4. Load first item
review_ui.load_next_item()

# Now the UI is interactive:
# - Review blob information and preview
# - Enter a reason for your decision
# - Click Keep, Delete, or Skip
# - Optionally save as training example
# - UI automatically loads next item
```

## Complete Workflow Example

```python
from dataatelier import Config, BlobCleanup
from dataatelier.ui import ReviewUI, create_progress_widget
from dataatelier.deletion import execute_deletion, dry_run_report
from dataatelier.storage import get_container_client
from IPython.display import display

# 1. Setup
config = Config(
    storage_connection_string="your_connection_string",
    container_name="your_container",
    llm_provider="openai",
    openai_api_key="your_api_key"
)

cleanup = BlobCleanup(config)

# 2. Create manifest
print("Creating manifest...")
manifest = cleanup.create_manifest()
print(f"Found {len(manifest)} blobs")

# 3. Run automatic triage
print("\nRunning LLM triage...")
while cleanup.get_unlabeled_count() > 0:
    stats = cleanup.run_triage_batch(batch_size=50)
    if stats['processed'] == 0:
        break
    print(f"  Processed {stats['processed']}, "
          f"{cleanup.get_unlabeled_count()} remaining")

# 4. Show progress
print("\nProgress:")
progress = cleanup.show_progress()
print(f"  Total: {progress['total_blobs']}")
print(f"  Auto-labeled: {progress['auto_labeled']}")
print(f"  Needs review: {progress['to_review']}")

# 5. Human review (in Jupyter notebook)
if progress['to_review'] > 0:
    print("\nStarting human review...")
    review_ui = ReviewUI(config)
    display(review_ui.create_widget())
    review_ui.load_next_item()

# 6. Dry run deletion report
print("\nDeletion dry run:")
dry_run = dry_run_report(config)
print(f"  Would delete {dry_run['total_to_delete']} blobs")
print(f"  Auto: {dry_run['by_source']['auto']}")
print(f"  Human: {dry_run['by_source']['human']}")

# 7. Execute deletion (if approved)
storage_client = get_container_client(config)
result = execute_deletion(config, dry_run=False, storage_client=storage_client)
print(f"\nDeleted {result['deleted_count']} blobs")
if result['failed_count'] > 0:
    print(f"Failed: {result['failed_count']}")

# 8. Archive for record keeping
archive_path = cleanup.archive_artifacts("./cleanup_archives")
print(f"\nArchived to: {archive_path}")
```

## Key Methods Reference

### BlobCleanup Class

| Method | Description | Returns |
|--------|-------------|---------|
| `create_manifest()` | List blobs and create manifest CSV | DataFrame |
| `run_triage_batch(batch_size)` | Run LLM triage on unlabeled blobs | dict with stats |
| `show_progress()` | Get current statistics | dict with counts |
| `get_unlabeled_count()` | Count unlabeled blobs | int |
| `archive_artifacts(archive_dir)` | Archive all artifacts | str (path) |
| `get_next_review_item()` | Get next review item | dict or None |

### ReviewUI Class

| Method | Description | Returns |
|--------|-------------|---------|
| `create_widget()` | Create interactive review widget | VBox widget |
| `load_next_item()` | Load next blob from review queue | bool |

### ProgressDisplay Class

| Method | Description | Returns |
|--------|-------------|---------|
| `create_widget()` | Create progress display widget | HTML widget |

## Features

✅ **Pure Python cleanup.py** - No Jupyter dependencies, can run in scripts  
✅ **Interactive ui.py** - Beautiful ipywidgets interface for notebooks  
✅ **Stateful Session** - Resume work at any time  
✅ **Full Audit Trail** - All decisions logged  
✅ **Safety Gates** - Conservative LLM with confidence thresholds  
✅ **Archiving** - Preserve all artifacts for compliance  
✅ **Type Hints** - Full type annotations  
✅ **Error Handling** - Comprehensive error handling  

## See Also

- [MODULES.md](MODULES.md) - Detailed module documentation
- [MODULE_USAGE.md](MODULE_USAGE.md) - Usage guide for llm, triage, deletion modules
- [README.md](README.md) - Main project documentation
