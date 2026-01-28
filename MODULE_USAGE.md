# DataAtelier Module Usage Guide

This guide explains how to use the three core modules: `llm`, `triage`, and `deletion`.

## llm.py - LLM Client Abstraction

### Creating an LLM Client

```python
from dataatelier import llm, Config

# Create config with your LLM provider settings
config = Config()
config.llm_provider = "openai"  # or "azure_openai" or "ollama"
config.openai_api_key = "your-api-key"
config.openai_model = "gpt-4"

# Create client using factory function
client = llm.create_llm_client(config)

# Or create directly
client = llm.OpenAIClient(api_key="your-key", model="gpt-4")
```

### Building Prompts and Parsing Responses

```python
from dataatelier.llm import build_triage_prompt, parse_llm_response
from dataatelier.policy import load_policy, load_few_shot_examples

# Load policy and examples
policy_text = load_policy("llm_policy.md")
examples = load_few_shot_examples("few_shot_examples.jsonl", max_examples=5)

# Build prompt
prompt = build_triage_prompt(
    metadata={'name': 'file.txt', 'size': 1024, ...},
    preview="File content preview...",
    policy=policy_text,
    examples=examples
)

# Call LLM and parse response
response = client.call(prompt, temperature=0.0)
parsed = parse_llm_response(response)
# Returns: {'label': 'keep'|'delete'|'human_review', 'confidence': 0.0-1.0, 'reason': '...'}
```

## triage.py - Triage Engine with Safety Gates

### Understanding the 3 Safety Gates

1. **Confidence Gate**: Only auto-label if confidence ≥ 0.95 (configurable)
2. **Self-Consistency Gate**: Multiple LLM runs must agree
3. **NEVER DELETE Gate**: Protects critical files from deletion

### Triaging Blobs

```python
from dataatelier import triage, Config
from dataatelier.models import BlobMetadata
from dataatelier.llm import create_llm_client

# Setup
config = Config()
config.confidence_threshold = 0.95
config.self_consistency_runs = 3
llm_client = create_llm_client(config)

# Triage a single blob
blob = BlobMetadata(
    name='temp_cache.txt',
    path='cache/temp_cache.txt',
    size=1024,
    last_modified=datetime.now(),
    content_type='text/plain',
    preview='...',
    # ... other fields
)

decision = triage.triage_blob(config, blob, llm_client)
print(f"Decision: {decision.label}")
print(f"Confidence: {decision.confidence}")
print(f"Reason: {decision.reason}")

# Triage multiple blobs
blobs = [blob1, blob2, blob3]
decisions = triage.batch_triage(config, blobs, llm_client)
```

### Using Individual Gates

```python
from dataatelier.triage import (
    check_confidence_gate,
    check_self_consistency_gate,
    check_never_delete_gate
)

# Gate 1: Confidence
passes = check_confidence_gate(confidence=0.98, threshold=0.95)

# Gate 2: Self-consistency
decisions = [decision1, decision2, decision3]
passes, agreed_decision = check_self_consistency_gate(decisions, min_agreement=1.0)

# Gate 3: NEVER DELETE
metadata = {'name': 'legal_contract.pdf', 'path': 'legal/...', ...}
passes = check_never_delete_gate(metadata, decision)
```

## deletion.py - Deletion Operations

### Dry Run and Coverage Check

```python
from dataatelier import deletion, Config

config = Config()

# Generate dry run report
report = deletion.dry_run_report(config)
print(f"Would delete {report['total_to_delete']} blobs")
print(f"Breakdown by source: {report['by_source']}")

# Check if all blobs are labeled
is_complete, unlabeled_count = deletion.check_coverage(config)
if not is_complete:
    print(f"Warning: {unlabeled_count} blobs are not labeled")
```

### Executing Deletions

```python
from dataatelier.deletion import execute_deletion
from dataatelier.storage import get_container_client

# Always start with dry run
result = execute_deletion(config, dry_run=True)
print(f"Dry run: {result['deleted_count']} blobs would be deleted")

# Review the dry run results, then execute for real
if result['coverage_check_passed']:
    storage_client = get_container_client(config)
    result = execute_deletion(config, dry_run=False, storage_client=storage_client)
    print(f"Deleted: {result['deleted_count']}")
    print(f"Failed: {result['failed_count']}")
    if result['errors']:
        print(f"Errors: {result['errors']}")
```

### Batch Deletion

```python
from dataatelier.deletion import delete_blobs_batch

# Delete specific blobs
blob_names = ['temp1.txt', 'temp2.txt', 'cache3.dat']
results = delete_blobs_batch(
    config,
    blob_names,
    dry_run=False,
    storage_client=storage_client
)

for res in results:
    if res['success']:
        print(f"✓ Deleted: {res['blob_name']}")
    else:
        print(f"✗ Failed: {res['blob_name']} - {res['error']}")
```

## Safety Features

### Conservative Decision-Making

All modules follow a conservative approach:
- **When in doubt, route to human review**
- Low confidence → human_review
- LLM disagreement → human_review
- NEVER DELETE triggers → human_review

### NEVER DELETE Protections

Files are protected from automatic deletion if they:
- Contain keywords: legal, contract, pii, invoice, financial, master, backup, production
- Are in retention folders: keep, preserve, archive, backup
- Were modified in the last 7 days
- Have ambiguous or mixed signals

### Coverage Requirement

Before executing deletions:
- System checks that 100% of blobs are labeled
- Prevents accidental deletion of unlabeled files
- Ensures explicit human or LLM decision for every blob

## Example: Complete Workflow

```python
from dataatelier import Config
from dataatelier.llm import create_llm_client
from dataatelier.triage import batch_triage
from dataatelier.deletion import execute_deletion
from dataatelier.storage import list_blobs, get_container_client
from dataatelier.queue import add_to_queue
from dataatelier.models import QueueEntry
from datetime import datetime

# 1. Setup
config = Config()
llm_client = create_llm_client(config)

# 2. List blobs
blobs = list_blobs(config)

# 3. Triage blobs
decisions = batch_triage(config, blobs, llm_client)

# 4. Add decisions to queues
for blob, decision in zip(blobs, decisions):
    queue_file = {
        'keep': config.to_keep_file,
        'delete': config.to_delete_file,
        'human_review': config.to_review_file
    }[decision.label]
    
    entry = QueueEntry(
        url=blob.url,
        container=blob.container,
        name=blob.name,
        decision=decision.label,
        reason=decision.reason,
        source='auto',
        decided_at=datetime.utcnow().isoformat(),
        policy_version=decision.policy_version,
        examples_version=decision.examples_version,
        confidence=decision.confidence
    )
    add_to_queue(queue_file, entry)

# 5. Review human_review queue manually
# (Use ReviewUI or manual inspection)

# 6. Dry run deletion
result = execute_deletion(config, dry_run=True)
print(f"Dry run: {result['deleted_count']} blobs marked for deletion")

# 7. Execute deletion (after review)
storage_client = get_container_client(config)
result = execute_deletion(config, dry_run=False, storage_client=storage_client)
print(f"Deleted {result['deleted_count']} blobs")
```

## Testing Without Azure/OpenAI

All modules accept clients/storage as parameters, making them testable:

```python
from dataatelier.llm import BaseLLMClient
from dataatelier.triage import triage_blob

class MockLLM(BaseLLMClient):
    def call(self, prompt, temperature=0.0):
        return '{"label": "delete", "confidence": 0.98, "reason": "Test"}'

# Test without real LLM
mock_client = MockLLM()
decision = triage_blob(config, blob, mock_client)
```

This design allows for:
- Unit testing without API keys
- Integration testing with mock services
- Development without cloud resources
