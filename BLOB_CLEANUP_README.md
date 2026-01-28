# Azure Blob Storage Cleanup Module

A comprehensive Python module for intelligent Azure Blob Storage cleanup with LLM-based triage, human-in-the-loop review, and full audit trail.

## Features

### 🤖 Conservative LLM-Based Triage
- **High confidence threshold**: ≥95% required for automatic decisions
- **Self-consistency checks**: Multiple LLM runs (3-5) must agree
- **Policy alignment**: Strict adherence to NEVER DELETE constraints
- **Multiple LLM providers**: OpenAI, Azure OpenAI, Ollama

### 🔍 Intelligent Text Extraction
Extracts previews from multiple file formats:
- Plain text files (`.txt`, `.log`, `.md`, `.csv`, `.json`, `.xml`)
- PDF documents (`.pdf`)
- Word documents (`.docx`)
- Automatic encoding detection
- Binary file detection

### 👤 Human-in-the-Loop Review
- **Interactive Jupyter notebook UI** with ipywidgets
- Visual preview of blob content
- LLM recommendation and reasoning display
- Simple Keep/Delete/Skip interface
- Progress tracking
- Full audit logging

### 📊 Queue Management
- **Three CSV-based queues**: to_review, to_delete, to_keep
- Easy queue inspection with pandas
- Move blobs between queues
- Batch operations

### 🧠 Few-Shot Learning
- Learn from human decisions
- Automatically incorporate review feedback
- Improve LLM accuracy over time
- Organization-specific pattern recognition

### 🔒 Safety & Audit
- **Dry-run mode** for testing
- Complete audit trail with timestamps
- Policy versioning (MD5 hashes)
- Conservative error handling (route to human review on errors)
- NEVER DELETE constraint enforcement

## Installation

```bash
pip install -r requirements.txt
```

### Requirements
```
azure-storage-blob>=12.19.0
pandas>=2.0.0
ipywidgets>=8.0.0
openai>=1.0.0
pdfminer.six>=20221105
python-docx>=1.0.0
chardet>=5.0.0
tiktoken>=0.5.0
python-dotenv>=1.0.0
tqdm>=4.65.0
```

## Quick Start

### 1. Configure Environment Variables

Create a `.env` file:

```bash
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_CONTAINER_NAME=my-container

# LLM Provider (choose one)
LLM_PROVIDER=openai  # or azure_openai or ollama
LLM_MODEL=gpt-4
LLM_API_KEY=sk-...

# Optional: Azure OpenAI specific
# LLM_ENDPOINT=https://my-resource.openai.azure.com/
# AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Optional: Ollama specific
# LLM_ENDPOINT=http://localhost:11434/v1

# Optional: Tune behavior
# CONFIDENCE_THRESHOLD=0.95
# SELF_CONSISTENCY_RUNS=3
# POLICY_FILE=llm_policy.md
```

### 2. One-Line Execution

```python
from dataatelier import quick_start

# Run complete workflow: inventory → triage → save to queues
cleanup = quick_start()
```

### 3. Review and Execute (in Jupyter Notebook)

```python
from dataatelier import create_cleanup_tool

# Create cleanup tool
cleanup = create_cleanup_tool()

# Run triage
cleanup.run_full_workflow()

# Interactive review
review_ui = cleanup.create_review_ui()
display(review_ui)

# After review, execute deletion
result = cleanup.deletion_manager.execute_deletion(dry_run=False)
print(f"Deleted {result['deleted_count']} blobs")
```

## Detailed Usage

### Manual Configuration

```python
from dataatelier import BlobCleanupConfig, AzureBlobCleanup

config = BlobCleanupConfig(
    connection_string="DefaultEndpointsProtocol=https;...",
    container_name="my-container",
    llm_provider="openai",
    llm_model="gpt-4",
    llm_api_key="sk-...",
    confidence_threshold=0.95,
    self_consistency_runs=3,
    policy_file="llm_policy.md",
    queue_dir="cleanup_queues",
)

cleanup = AzureBlobCleanup(config)
```

### Step-by-Step Workflow

```python
# 1. Create inventory with text previews
manifest = cleanup.inventory.create_manifest(prefix="logs/")

# 2. Run LLM triage
decisions = cleanup.llm_engine.batch_triage(manifest)

# 3. Save to queues
cleanup.queue_manager.save_triage_decisions(manifest, decisions)

# 4. Get statistics
stats = cleanup.get_statistics()
print(f"To Review: {stats['review']['count']} blobs")
print(f"To Delete: {stats['delete']['count']} blobs")
print(f"To Keep: {stats['keep']['count']} blobs")
```

### Using Azure OpenAI

```python
config = BlobCleanupConfig(
    connection_string="...",
    container_name="my-container",
    llm_provider="azure_openai",
    llm_model="gpt-4",
    llm_api_key="<azure-openai-key>",
    llm_endpoint="https://my-resource.openai.azure.com/",
    llm_api_version="2024-02-15-preview",
)
```

### Using Ollama (Local LLM)

```python
config = BlobCleanupConfig(
    connection_string="...",
    container_name="my-container",
    llm_provider="ollama",
    llm_model="llama2",
    llm_endpoint="http://localhost:11434/v1",
)
```

### Deletion Workflow

```python
# Dry run analysis
dry_run_result = cleanup.deletion_manager.dry_run()
print(f"Would delete: {dry_run_result['total_blobs']} blobs")
print(f"Total size: {dry_run_result['total_size_mb']:.2f} MB")

# Dry run execution (simulate)
result = cleanup.deletion_manager.execute_deletion(dry_run=True)
print(f"Dry run: would delete {result['deleted_count']} blobs")

# Actual deletion (be careful!)
result = cleanup.deletion_manager.execute_deletion(dry_run=False)
print(f"Deleted {result['deleted_count']} blobs")
```

### Few-Shot Learning

```python
from dataatelier import BlobMetadata
from datetime import datetime, timezone

# Add human decision examples
blob_meta = BlobMetadata(
    name="temp/debug.log",
    size=1024,
    last_modified=datetime.now(timezone.utc),
    content_type="text/plain",
    etag="abc",
    preview="Debug log content..."
)

cleanup.llm_engine.add_few_shot_example(
    blob_meta=blob_meta,
    decision="DELETE",
    reasoning="Debug log older than retention period"
)

# The LLM will use this example in future decisions
```

## Architecture

### Core Classes

#### `BlobCleanupConfig`
Configuration management with environment variable support.

```python
config = BlobCleanupConfig.from_env()
errors = config.validate()
```

#### `BlobInventory`
Handles blob listing and preview extraction.

```python
inventory = BlobInventory(config)
manifest = inventory.create_manifest(prefix="logs/")
```

#### `LLMTriageEngine`
Conservative LLM-based decision making with multiple safety gates.

```python
engine = LLMTriageEngine(config)
decision = engine.triage_blob(blob_metadata)
```

#### `QueueManager`
CSV-based queue management.

```python
queue_mgr = QueueManager(config)
df = queue_mgr.load_queue("review")
queue_mgr.remove_from_queue("review", ["blob1.txt"])
```

#### `ReviewUI`
Interactive Jupyter notebook interface.

```python
ui = ReviewUI(config, queue_manager, llm_engine)
ui.load_review_queue()
widget = ui.create_review_interface()
```

#### `DeletionManager`
Safe deletion with dry-run support.

```python
deletion_mgr = DeletionManager(config, queue_manager)
result = deletion_mgr.execute_deletion(dry_run=True)
```

#### `AzureBlobCleanup`
Main orchestrator combining all components.

```python
cleanup = AzureBlobCleanup(config)
cleanup.run_full_workflow()
```

## Policy File

The module uses a policy file (default: `llm_policy.md`) that defines cleanup rules. See the provided `llm_policy.md` for the format.

Key sections:
- **Positive signals for DELETE**: Temporary files, old logs, duplicates
- **Positive signals for KEEP**: Business documents, customer data, recent files
- **NEVER DELETE**: Legal holds, PII (requires human approval), active data
- **Edge cases**: Route to human review when uncertain

Policy versioning:
- MD5 hash of policy is computed
- Hash stored with each decision
- Enables audit trail of which policy version was used

## Queue Files

The module creates CSV files in the queue directory (default: `cleanup_queues/`):

- **`to_review.csv`**: Blobs requiring human review
- **`to_delete.csv`**: Blobs approved for deletion
- **`to_keep.csv`**: Blobs approved for retention
- **`audit_log.csv`**: Complete audit trail

Each queue contains:
- Blob metadata (name, size, last_modified, content_type, etag)
- Text preview
- LLM decision and reasoning
- Confidence score
- Self-consistency score
- Policy hash
- Timestamp

## Conservative Decision Gates

The LLM triage applies multiple safety gates:

1. **Self-Consistency Check**: Multiple LLM runs (3-5) must agree (≥80% consensus)
2. **Confidence Threshold**: Must be ≥0.95 for automatic DELETE/KEEP
3. **NEVER DELETE Check**: Scans for keywords (legal, compliance, audit, PII, etc.)
4. **Recent Activity Check**: Blobs modified in last 7 days routed to review
5. **Error Handling**: Any triage error routes to human review

If any gate fails, decision is downgraded to `HUMAN_REVIEW`.

## Examples

See `dataatelier/example_usage.py` for comprehensive examples:
- Basic usage with environment variables
- Manual configuration
- Azure OpenAI configuration
- Ollama (local LLM) configuration
- Step-by-step workflow
- Deletion workflow
- Few-shot learning
- Custom policy files

## Security Considerations

1. **Never commit credentials**: Use environment variables or `.env` file (add to `.gitignore`)
2. **Test with dry-run first**: Always use `dry_run=True` before actual deletion
3. **Review NEVER DELETE constraints**: Customize policy for your organization
4. **Audit trail**: All actions logged to `audit_log.csv`
5. **Policy versioning**: Track which policy version made each decision

## Limitations

- **LLM costs**: Each blob requires multiple LLM calls (self-consistency)
- **Rate limits**: Built-in delays between calls, but may need tuning
- **Large files**: Preview extraction limited to configurable size (default 10 MB)
- **Binary files**: Limited preview for non-text files
- **Token limits**: Preview text truncated to fit LLM context window

## Troubleshooting

### "Configuration errors: AZURE_STORAGE_CONNECTION_STRING is required"
Set environment variables in `.env` file or system environment.

### "Failed to load policy: [Errno 2] No such file or directory"
Ensure `llm_policy.md` exists or specify correct path in config.

### "LLM call failed: RateLimitError"
Reduce batch size or increase delays between calls.

### "No blobs to review"
Run `cleanup.run_full_workflow()` first to populate queues.

## Contributing

Contributions welcome! Please ensure:
- Type hints for all functions
- Docstrings for classes and methods
- Error handling with meaningful messages
- Unit tests for new features

## License

[Your license here]

## Support

For issues or questions:
- Check `example_usage.py` for common patterns
- Review `llm_policy.md` for policy format
- Consult source code docstrings
- Open an issue on GitHub

## Acknowledgments

Built with:
- Azure SDK for Python
- OpenAI Python SDK
- pdfminer.six, python-docx for document parsing
- ipywidgets for interactive UI
- pandas for data management
