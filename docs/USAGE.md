# Usage Examples

## Basic Usage

### 1. Manual Mode (No LLM)

If you just want to manually review and label files without LLM assistance:

```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --llm-off
```

This will:
1. Inventory all blobs in the container
2. Open the TUI for manual review
3. You can mark items as Keep/Delete/Review using keyboard shortcuts

### 2. LLM-Assisted Mode

With OpenAI or Azure OpenAI configured:

```bash
# Set your API key
export OPENAI_API_KEY="sk-..."

# Run with LLM assistance
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --llm-model gpt-4
```

The LLM will automatically classify items in the background. Items with high confidence (≥95%) will be auto-labeled, others will go to the review queue.

### 3. Limited Scope Testing

Test on a subset of files:

```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --prefix "logs/2024/" \
  --max-files 100
```

### 4. Resume Previous Session

If you already have a manifest from a previous run:

```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --skip-inventory
```

## TUI Workflow

### Navigation
- Use `j`/`k` or arrow keys to move through the list
- Press `Enter` to view item details in the preview panel
- Press `R` to refresh the queue

### Labeling Items
- Press `K` to mark as **Keep**
- Press `D` to mark for **Delete**
- Press `H` to mark for **Human Review**

### Working with Policy and Examples

#### Edit Policy
1. Press `E` to open the policy file in your editor
2. Update the policy with specific rules for your use case
3. Save and close the editor
4. The LLM will use the updated policy for future classifications

Example policy update:
```markdown
## Never-Delete Clauses
1. Never delete files in /production/ or /prod/
2. Never delete files with "customer" in the name
3. Never delete files modified in the last 7 days
4. Never delete .config or .yaml files
```

#### Add Few-Shot Examples
1. Navigate to an item that you've labeled
2. Press `A` to add it as an example
3. Enter a reason and optional cues
4. The example will be used to train future LLM classifications

### Running LLM Triage
- Press `T` to toggle the background LLM worker on/off
- Press `G` to manually trigger a batch of classifications

### Check Progress
- Press `C` to view coverage statistics
- The status bar shows real-time counts

### Deletion

When you're ready to delete:

1. Ensure 100% of items are labeled (check with `C`)
2. Press `X` to start the deletion process
3. Review the dry-run summary
4. Type `DELETE {count}` exactly to confirm
5. Blobs will be deleted and logged to audit_log.csv

## Advanced Usage

### Using Azure OpenAI

```bash
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://myresource.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2023-12-01-preview"

python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --azure-openai
```

### Custom Work Directory

To keep multiple cleanup sessions separate:

```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --work-dir ./cleanup-session-1
```

All state files (manifest, queues, audit log, etc.) will be stored in `./cleanup-session-1/`.

### Tuning LLM Behavior

```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --confidence 0.98 \           # Higher threshold = more conservative
  --self-consistency 5 \         # More passes = more reliable
  --llm-model gpt-3.5-turbo     # Faster/cheaper model
```

## Workflow Example

Complete workflow for cleaning up old logs:

```bash
# 1. Start with limited scope
python azure_blob_cleanup_tui.py run \
  --container logs \
  --prefix "app-logs/2023/" \
  --max-files 500 \
  --llm-model gpt-4

# 2. In TUI:
#    - Press T to start LLM worker
#    - Wait for auto-classification
#    - Review items in "to_review" queue
#    - Press E to edit policy if needed
#    - Add examples with A for edge cases
#    - Label remaining items with K/D

# 3. When satisfied:
#    - Press C to check 100% coverage
#    - Press X to delete
#    - Type DELETE {count} to confirm

# 4. Archive results
blob-cleanup archive --work-dir .
```

## Viewing Results

### Check Statistics
```bash
blob-cleanup stats --work-dir .
```

### View Files
All state files are CSV/JSON/JSONL for easy inspection:

```bash
# View manifest
cat manifest.csv | head

# View items marked for deletion
cat to_delete.csv

# View audit log
cat audit_log.csv | tail -20

# View few-shot examples
cat few_shot_examples.jsonl
```

### Export Data

State files can be opened in Excel, imported into databases, or processed with pandas:

```python
import pandas as pd

# Analyze what's being deleted
df = pd.read_csv('to_delete.csv')
print(df.groupby('reason')['name'].count())

# Review LLM predictions
predictions = pd.read_parquet('llm_predictions.parquet')
print(predictions.describe())
```

## Troubleshooting

### "No module named 'azure'"
Install dependencies:
```bash
pip install -r requirements.txt
```

### "Azure Storage credentials not configured"
Set environment variables:
```bash
export AZURE_STORAGE_CONNECTION_STRING="..."
```

### LLM not working
Check API key:
```bash
export OPENAI_API_KEY="sk-..."
```

Or use manual mode:
```bash
python azure_blob_cleanup_tui.py run --container mycontainer --llm-off
```

### "Cannot delete: only X% labeled"
All items must be labeled before deletion. Review remaining items or mark them to complete labeling.
