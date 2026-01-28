# DataAtelier Modular Python Modules

This document describes the pure Python modules in the DataAtelier package. These modules provide reusable, testable functions with NO Jupyter dependencies.

## Overview

The DataAtelier package now includes modular components that can be used independently or together:

- **storage.py** - Azure Blob Storage operations
- **extractors.py** - Text extraction from various formats
- **policy.py** - Policy and examples management
- **queue.py** - CSV-based queue management
- **audit.py** - Audit logging
- **models.py** - Data models
- **config.py** - Configuration management

## Module Details

### 1. storage.py - Azure Blob Storage Operations

Provides functions for interacting with Azure Blob Storage.

**Functions:**
- `get_container_client(config)` → ContainerClient
- `list_blobs(config, name_prefix=None)` → list[BlobMetadata]
- `download_blob_content(config, blob_name, max_bytes=None)` → bytes
- `delete_blob(config, blob_name)` → bool

**Example:**
```python
from dataatelier import storage, Config

config = Config(
    storage_connection_string="...",
    container_name="my-container"
)

# List all blobs
blobs = storage.list_blobs(config)

# Download blob content
content = storage.download_blob_content(config, "myfile.txt", max_bytes=4096)

# Delete a blob
storage.delete_blob(config, "oldfile.txt")
```

### 2. extractors.py - Text Extraction

Extracts text from various file formats using appropriate libraries.

**Functions:**
- `robust_decode(data: bytes)` → str
  - Uses chardet for automatic encoding detection
- `extract_text_preview(content: bytes, content_type: str, max_bytes: int)` → str
  - Supports: txt, json, xml, csv, pdf (pdfminer.six), docx (python-docx)

**Example:**
```python
from dataatelier import extractors

# Decode bytes with automatic encoding detection
text = extractors.robust_decode(data)

# Extract text from various formats
txt_preview = extractors.extract_text_preview(content, "text/plain", 4096)
pdf_preview = extractors.extract_text_preview(pdf_content, "application/pdf", 4096)
docx_preview = extractors.extract_text_preview(docx_content, ".docx", 4096)
```

### 3. policy.py - Policy and Examples Management

Manages policy documents and few-shot learning examples.

**Functions:**
- `load_policy(file_path)` → str
- `get_policy_version(file_path)` → str (MD5 hash)
- `load_few_shot_examples(file_path, max_examples=-1, balance=True)` → list[FewShotExample]
- `get_examples_version(file_path)` → str (MD5 hash)
- `save_few_shot_example(file_path, example)` → None

**Example:**
```python
from dataatelier import policy
from dataatelier import FewShotExample

# Load policy
policy_text = policy.load_policy("llm_policy.md")
version = policy.get_policy_version("llm_policy.md")

# Save a few-shot example
example = FewShotExample(
    label="keep",
    reason="Business document",
    excerpt="Invoice #12345",
    path_hint="invoices/2024/",
    content_type="application/pdf",
    date="2024-01-15",
    reviewer="alice"
)
policy.save_few_shot_example("examples.jsonl", example)

# Load examples with balancing
examples = policy.load_few_shot_examples("examples.jsonl", max_examples=10, balance=True)
```

### 4. queue.py - CSV Queue Management

Manages CSV-based processing queues.

**Functions:**
- `initialize_queues(queue_paths)` → None
- `load_queue(file_path)` → list[QueueEntry]
- `save_queue(file_path, entries)` → None
- `add_to_queue(file_path, entry)` → None
- `remove_from_queue(file_path, blob_name)` → None
- `get_unlabeled_blobs(manifest_path, queue_paths)` → DataFrame
- `get_statistics(config)` → dict

**Example:**
```python
from dataatelier import queue, Config, QueueEntry
from datetime import datetime

config = Config()
config.to_keep_file = "to_keep.csv"
config.to_delete_file = "to_delete.csv"
config.to_review_file = "to_review.csv"

# Initialize queues
queue.initialize_queues([config.to_keep_file, config.to_delete_file, config.to_review_file])

# Add entry to queue
entry = QueueEntry(
    url="https://example.com/blob.txt",
    container="test",
    name="blob.txt",
    decision="keep",
    reason="Important file",
    source="human",
    decided_at=datetime.now().isoformat(),
    policy_version="v1",
    examples_version="v1",
    confidence=1.0
)
queue.add_to_queue(config.to_keep_file, entry)

# Get statistics
stats = queue.get_statistics(config)
print(f"Total: {stats['total_blobs']}, Labeled: {stats['labeled']}")
```

### 5. audit.py - Audit Logging

Provides audit trail functionality.

**Functions:**
- `log_audit(file_path, entry)` → None
- `load_audit_log(file_path, blob_name=None, action=None)` → list[AuditEntry]

**Example:**
```python
from dataatelier import audit
from dataatelier import AuditEntry
from datetime import datetime

# Log an audit entry
entry = AuditEntry(
    timestamp=datetime.now().isoformat(),
    blob_name="myfile.txt",
    action="deleted",
    source="human",
    reason="User confirmed deletion",
    metadata='{"confidence": 0.99}'
)
audit.log_audit("audit_log.csv", entry)

# Load audit log
all_entries = audit.load_audit_log("audit_log.csv")
deleted_entries = audit.load_audit_log("audit_log.csv", action="deleted")
```

### 6. models.py - Data Models

Data classes for the DataAtelier package.

**Models:**
- `BlobMetadata` - Metadata for Azure blobs
- `TriageDecision` - LLM triage decision
- `QueueEntry` - Entry in processing queue
- `AuditEntry` - Entry in audit log
- `FewShotExample` - Few-shot learning example

**Example:**
```python
from dataatelier.models import BlobMetadata, QueueEntry, FewShotExample
from datetime import datetime

# Create blob metadata
blob = BlobMetadata(
    url="https://...",
    container="test",
    name="file.txt",
    path="folder/file.txt",
    size=1024,
    last_modified=datetime.now(),
    content_type="text/plain",
    etag="abc123",
    preview="File content preview...",
    preview_length=100
)

# Convert to dictionary
blob_dict = blob.to_dict()
```

### 7. config.py - Configuration

Configuration management for the package.

**Class:**
- `Config` - Configuration with environment variable support

**Example:**
```python
from dataatelier import Config

# Create config
config = Config(
    storage_connection_string="...",
    container_name="my-container",
    llm_provider="openai",
    openai_api_key="...",
    confidence_threshold=0.95
)

# Validate config
errors = config.validate()
if errors:
    print("Configuration errors:", errors)
```

## Key Features

✅ **Pure Python** - No Jupyter dependencies  
✅ **Type Hints** - Full type annotations on all functions  
✅ **Docstrings** - Comprehensive documentation  
✅ **Error Handling** - Graceful error handling with descriptive messages  
✅ **Testable** - Can be tested without external services  
✅ **Pandas Integration** - Uses pandas for CSV operations  
✅ **Security** - Zero vulnerabilities (CodeQL verified)  
✅ **Backward Compatible** - Works alongside existing blob_cleanup module  

## Testing

All modules can be imported and tested independently:

```python
from dataatelier import storage, extractors, policy, queue, audit
from dataatelier import Config, QueueEntry, AuditEntry, FewShotExample

# Test extraction
text = extractors.robust_decode(b"Hello World")

# Test policy
policy_text = policy.load_policy("llm_policy.md")

# Test queue operations
queue.initialize_queues(["queue.csv"])
```

## Dependencies

The modules use the following external libraries:

- **azure-storage-blob** - Azure Blob Storage operations
- **pandas** - CSV operations
- **chardet** - Character encoding detection
- **pdfminer.six** - PDF text extraction
- **python-docx** - DOCX text extraction

All dependencies are listed in `requirements.txt`.
