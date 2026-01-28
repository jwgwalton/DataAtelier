# DataAtelier Examples

This directory contains practical examples showing how to use the Azure Blob Cleanup TUI in various scenarios.

## Available Examples

### 1. Basic Usage (`basic_usage.py`)
The simplest way to get started with the tool. Shows:
- Environment setup
- Running the application
- Basic TUI navigation
- Key shortcuts

**Run it:**
```bash
python examples/basic_usage.py
```

### 2. Manual Mode (`manual_mode.py`)
How to use the tool without LLM assistance. Perfect when:
- You don't have an OpenAI API key
- You prefer full manual control
- You have a small dataset
- Classification requires human judgment

**Run it:**
```bash
python examples/manual_mode.py
```

### 3. Custom Policy (`with_policy.py`)
How to customize the LLM policy for your specific use case. Shows:
- Writing effective policies
- Never-delete clauses
- Retention rules
- Adding few-shot examples

**Run it:**
```bash
python examples/with_policy.py
```

## Quick Start Guide

### Prerequisites
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up Azure Storage credentials (choose one):
   ```bash
   # Option 1: Connection string
   export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;..."
   
   # Option 2: Account URL + SAS token
   export AZURE_STORAGE_ACCOUNT_URL="https://myaccount.blob.core.windows.net"
   export AZURE_STORAGE_SAS_TOKEN="?sv=..."
   ```

3. (Optional) Set up OpenAI API key for LLM features:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

### Basic Workflow

1. **Inventory** - List and preview blobs:
   ```bash
   python azure_blob_cleanup_tui.py run --container mycontainer
   ```

2. **Review** - Use TUI to label files:
   - `K` = Keep
   - `D` = Delete
   - `H` = Human review
   - `?` = Help

3. **Delete** - Execute deletion when ready:
   - Press `X`
   - Type `DELETE {count}` to confirm

## Common Scenarios

### Scenario 1: Clean Up Old Logs
```bash
python azure_blob_cleanup_tui.py run \
  --container logs \
  --prefix "app-logs/2023/" \
  --llm-model gpt-4
```

### Scenario 2: Manual Review of Test Data
```bash
python azure_blob_cleanup_tui.py run \
  --container test-data \
  --max-files 100 \
  --llm-off
```

### Scenario 3: Production Cleanup with Custom Policy
```bash
# 1. Create work directory
mkdir cleanup-prod
cd cleanup-prod

# 2. Create custom llm_policy.md (see with_policy.py example)

# 3. Run with custom policy
python azure_blob_cleanup_tui.py run \
  --container production \
  --work-dir . \
  --confidence 0.98
```

### Scenario 4: Resume Previous Session
```bash
python azure_blob_cleanup_tui.py run \
  --container mycontainer \
  --skip-inventory
```

## Tips

### For Better LLM Classification
1. **Start with a custom policy** - Generic policies work, but specific ones are better
2. **Add examples as you go** - Press `A` to add good examples
3. **Tune confidence threshold** - Use `--confidence 0.98` for more conservative
4. **Use self-consistency** - Higher `--self-consistency` is more reliable

### For Efficient Workflow
1. **Use filters** - Press `/` to filter by name/path
2. **Batch operations** - Press `B` for batch mode
3. **Check coverage** - Press `C` to see progress
4. **Archive results** - Run `blob-cleanup archive` when done

### For Safety
1. **Test with limits** - Use `--max-files 100` first
2. **Review auto-deletes** - Check items LLM marked for deletion
3. **Use dry-run** - Review delete list before confirming
4. **Archive before deleting** - Keep a backup of state files

## Troubleshooting

### "No module named 'azure'"
```bash
pip install -r requirements.txt
```

### "Azure Storage credentials not configured"
```bash
export AZURE_STORAGE_CONNECTION_STRING="..."
```

### "LLM worker not running"
- Check `OPENAI_API_KEY` is set
- Or use `--llm-off` for manual mode
- Press `T` in TUI to toggle worker

### "Cannot delete: only X% labeled"
- All items must be labeled (Keep or Delete)
- Review remaining items or use batch mode
- Check coverage with `C` key

## More Information

- **Full Documentation**: See `README.md`
- **Usage Guide**: See `docs/USAGE.md`
- **Contributing**: See `CONTRIBUTING.md`

## Example Output

When you run an example, you'll see:
```
🚀 Initializing Azure Blob Cleanup Assistant
✓ Connected to Azure Storage
✓ Initialized state manager (work dir: .)
✓ Loaded policy (version: a1b2c3d4)
✓ Loaded examples (keep: 5, delete: 8)
✓ Initialized LLM triage (model: gpt-4)

📋 Starting inventory for container: mycontainer
⏳ Listing blobs...
✓ Found 247 blobs

⏳ Generating previews...
   Progress: 247/247
✓ Manifest updated

🎨 Starting TUI application...
Press ? for help, Q to quit
```

Then the TUI interface opens for interactive review!
