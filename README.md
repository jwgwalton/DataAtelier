# DataAtelier

A human-in-the-loop data cleansing tool for Azure Blob Storage that leverages LLMs for scale.

## Overview

DataAtelier is a lightweight, terminal-based (TUI) application for cleaning up Azure Blob Storage with intelligent LLM-assisted triage and human oversight. It helps you:

- 📋 Inventory and preview blobs in Azure Storage
- 🤖 Automatically classify files using LLM (keep/delete/review)
- 👤 Review and label files with an interactive TUI
- 🔒 Safely delete files with confirmation and audit trails
- 📚 Learn from your decisions with few-shot examples

## Features

- **Single TUI Application**: Terminal-based interface drives the entire workflow
- **Conservative LLM Triage**: Auto-accepts only when completely certain (95%+ confidence)
- **Human-in-the-Loop**: Final decisions always under human control
- **Local State Management**: CSV/JSON/Parquet files for auditability
- **Policy & Examples**: Evolving policy file and few-shot examples improve LLM accuracy
- **Safe Deletion**: 100% labeling required, confirmation gate, full audit log

## Installation

### Prerequisites

- Python 3.9 or higher
- Azure Storage account with container access
- (Optional) OpenAI API key or Azure OpenAI access for LLM features

### Install

```bash
# Clone the repository
git clone https://github.com/jwgwalton/DataAtelier.git
cd DataAtelier

# Install dependencies
pip install -r requirements.txt

# Or install with pip (editable mode)
pip install -e .
```

## Configuration

Set up your environment variables:

```bash
# Azure Storage (required)
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=..."
# OR
export AZURE_STORAGE_ACCOUNT_URL="https://youraccout.blob.core.windows.net"
export AZURE_STORAGE_SAS_TOKEN="?sv=..."  # Optional

# Azure Blob Container (required)
export AZURE_BLOB_CONTAINER="mycontainer"

# Optional: prefix filter
export AZURE_BLOB_PREFIX="logs/"

# OpenAI (for LLM features)
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4"  # or gpt-3.5-turbo

# OR Azure OpenAI
# export AZURE_OPENAI_API_KEY="..."
# export AZURE_OPENAI_ENDPOINT="https://..."
# export AZURE_OPENAI_API_VERSION="2023-12-01-preview"

# Optional: tuning
export CERTAINTY_CONF_THRESHOLD="0.95"
export SELF_CONSISTENCY_PASSES="3"
export PREVIEW_MAX_BYTES="4096"
export WORK_DIR="."
```

Or create a `.env` file with these variables.

## Usage

### Quick Start

```bash
# Run the TUI application
python azure_blob_cleanup_tui.py --container mycontainer

# Or if installed
blob-cleanup run --container mycontainer
```

### CLI Options

```bash
# Full options
blob-cleanup run \
  --container mycontainer \
  --prefix "logs/2023/" \
  --max-files 100 \
  --preview-bytes 4096 \
  --work-dir ./cleanup-session \
  --llm-model gpt-4 \
  --confidence 0.95 \
  --self-consistency 3

# Skip inventory (use existing manifest)
blob-cleanup run --container mycontainer --skip-inventory

# Disable LLM (manual mode only)
blob-cleanup run --container mycontainer --llm-off

# Use Azure OpenAI
blob-cleanup run --container mycontainer --azure-openai
```

### Other Commands

```bash
# Show statistics
blob-cleanup stats

# Archive artifacts
blob-cleanup archive
```

## TUI Key Bindings

| Key | Action |
|-----|--------|
| `j/k` or `↓/↑` | Navigate items |
| `Enter` | View item details |
| `K` | Mark as Keep |
| `D` | Mark as Delete |
| `H` or `Space` | Mark for Human Review |
| `R` | Refresh queues |
| `/` | Search/filter |
| `F` | Toggle filters |
| `B` | Batch action mode |
| `A` | Add as few-shot example |
| `E` | Edit policy (external editor) |
| `G` | Run LLM triage now |
| `T` | Toggle LLM worker on/off |
| `C` | View coverage stats |
| `X` | Execute deletion (when 100% labeled) |
| `?` | Show help |
| `Q` | Quit |

## Workflow

1. **Inventory**: App lists blobs and generates previews
2. **LLM Triage**: Background worker classifies files (keep/delete/review)
3. **Human Review**: Review and label items in TUI
4. **Learn**: Add examples and edit policy to improve LLM
5. **Delete**: When 100% labeled, execute deletion with confirmation

## Architecture

```
azure_blob_cleanup_tui.py  - Main entry point
lib/
  ├── storage_io.py         - Azure Blob Storage operations
  ├── state.py              - State management (CSV/Parquet)
  ├── policy.py             - Policy file management
  ├── examples.py           - Few-shot examples (JSONL)
  ├── triage_llm.py         - LLM classification logic
  └── tui_app.py            - Textual TUI application

Runtime artifacts:
  ├── manifest.csv          - Blob inventory
  ├── to_review.csv         - Items pending review
  ├── to_delete.csv         - Items marked for deletion
  ├── to_keep.csv           - Items marked to keep
  ├── audit_log.csv         - Full audit trail
  ├── llm_predictions.parquet - LLM predictions cache
  ├── few_shot_examples.jsonl - Training examples
  └── llm_policy.md         - Classification policy
```

## LLM Certainty Gates

The LLM auto-accepts keep/delete decisions only when ALL of these are true:

1. **Confidence ≥ 0.95** (configurable)
2. **Self-consistency**: Multiple passes agree on the same label
3. **Policy alignment**: No violation of never-delete clauses

Otherwise, items go to the human review queue.

## Safety Features

- **100% Labeling Required**: Cannot delete until every blob is labeled
- **Confirmation Gate**: Must type "DELETE {count}" to proceed
- **Audit Log**: Every action logged with timestamp and actor
- **Archive**: All artifacts can be archived before deletion
- **Dry Run**: Review deletion list before executing

## Example Session

```bash
# Start the application
$ blob-cleanup run --container mydata --prefix "temp/"

📋 Starting inventory for container: mydata
   Prefix filter: temp/
⏳ Listing blobs...
✓ Found 247 blobs

⏳ Generating previews...
   Progress: 247/247
✓ Manifest updated

🤖 LLM triage started (worker ON)
   Auto-classified: 180 keep, 45 delete, 22 review

👤 Human review: 22 items
   [K] Keep | [D] Delete | [H] Review
   [A] Add example | [E] Edit policy

✓ Coverage: 247/247 (100%)
   To delete: 45 blobs

🗑️  Execute deletion?
   Type "DELETE 45" to confirm: DELETE 45
   ✓ Deleted 45 blobs

📦 Archive artifacts? [Y/n]: y
   ✓ Archived to: ./archive/20260128_162500/

✓ Session complete
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Format code
black .

# Lint
ruff check .

# Run tests (when added)
pytest
```

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.

## Acknowledgments

Built with:
- [Textual](https://github.com/Textualize/textual) - Modern TUI framework
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal output
- [Azure SDK for Python](https://github.com/Azure/azure-sdk-for-python)
- [OpenAI Python](https://github.com/openai/openai-python)
