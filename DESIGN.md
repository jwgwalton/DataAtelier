# DataAtelier - Modular Architecture Design

## Overview
Rebuild as a properly modular Python package where:
- Core logic is in testable Python modules (no Jupyter dependencies)
- Jupyter notebook is only the human interface layer
- All business logic can be tested without notebooks

## Module Structure

```
dataatelier/
├── __init__.py              # Package exports
├── config.py                # Configuration management
├── models.py                # Data models (dataclasses)
├── storage.py               # Azure Blob Storage operations
├── extractors.py            # Text extraction from various formats
├── llm.py                   # LLM client abstraction
├── triage.py                # Triage engine with safety gates
├── queue.py                 # Queue management (CSV operations)
├── audit.py                 # Audit logging
├── policy.py                # Policy loading and versioning
├── deletion.py              # Deletion operations
├── ui.py                    # Jupyter UI components (ipywidgets)
└── cleanup.py               # Main orchestrator

tests/
├── __init__.py
├── test_config.py
├── test_models.py
├── test_storage.py
├── test_extractors.py
├── test_llm.py
├── test_triage.py
├── test_queue.py
├── test_audit.py
├── test_policy.py
├── test_deletion.py
└── test_cleanup.py

notebooks/
└── azure_blob_cleanup.ipynb  # Human interface only
```

## Design Principles

1. **Separation of Concerns**: Each module has a single responsibility
2. **Testability**: All core logic can be unit tested without Jupyter
3. **Dependency Injection**: Use interfaces, not hard-coded dependencies
4. **Type Safety**: Full type hints for all public APIs
5. **Error Handling**: Comprehensive error handling with custom exceptions
6. **Documentation**: Docstrings for all public functions and classes

## Module Responsibilities

### config.py
- Load environment variables
- Provide configuration object
- No external dependencies (just os, typing)

### models.py
- Data classes for BlobMetadata, TriageDecision, QueueEntry, etc.
- Pure data structures, no business logic
- Use dataclasses for immutability

### storage.py
- List blobs from Azure Storage
- Download blob content
- Delete blobs
- All Azure-specific operations

### extractors.py
- Extract text from various file formats
- Robust encoding detection
- Format-specific extractors (PDF, DOCX, etc.)
- Returns plain text strings

### llm.py
- Abstract LLM client interface
- Concrete implementations: OpenAI, Azure OpenAI, Ollama
- Prompt building
- JSON response parsing

### triage.py
- Implements the 3 safety gates
- Self-consistency checking
- Policy alignment verification
- Returns TriageDecision objects

### queue.py
- Load/save CSV queues
- Add/remove queue entries
- Get unlabeled blobs
- Queue statistics

### audit.py
- Append-only audit log
- Structured logging
- Query audit history

### policy.py
- Load policy from markdown file
- Calculate policy version (MD5 hash)
- Load/save few-shot examples
- Examples version tracking

### deletion.py
- Dry-run reporting
- Actual deletion execution
- Safety checks (100% coverage)
- Batch deletion with progress

### ui.py
- ReviewUI widget (ipywidgets)
- Progress display widgets
- Only this module depends on ipywidgets/IPython

### cleanup.py
- Main orchestrator class
- Coordinates all modules
- High-level workflow methods
- Stateful session management

## TODO List

- [ ] 1. Create module structure
  - [ ] Create all module files with docstrings
  - [ ] Define interfaces and type hints
  
- [ ] 2. Implement core modules (no external dependencies)
  - [ ] config.py
  - [ ] models.py
  
- [ ] 3. Implement Azure integration
  - [ ] storage.py
  - [ ] extractors.py
  
- [ ] 4. Implement LLM integration
  - [ ] llm.py
  - [ ] triage.py
  
- [ ] 5. Implement data management
  - [ ] queue.py
  - [ ] audit.py
  - [ ] policy.py
  
- [ ] 6. Implement operations
  - [ ] deletion.py
  - [ ] cleanup.py (orchestrator)
  
- [ ] 7. Implement UI layer
  - [ ] ui.py (Jupyter widgets)
  
- [ ] 8. Create tests
  - [ ] Unit tests for all modules
  - [ ] Integration tests
  - [ ] Mock Azure/LLM dependencies
  
- [ ] 9. Update notebook
  - [ ] Simple notebook that imports modules
  - [ ] Focus on human interaction
  - [ ] Clean, documented examples
  
- [ ] 10. Documentation
  - [ ] README with architecture
  - [ ] API documentation
  - [ ] Usage examples

## Testing Strategy

### Unit Tests
- Each module has its own test file
- Mock external dependencies (Azure, OpenAI)
- Test edge cases and error handling
- 80%+ code coverage target

### Integration Tests
- Test module interactions
- Use test fixtures for file I/O
- Mock network calls

### Manual Testing
- Notebook-based manual testing
- Real Azure Storage (test container)
- Small dataset for validation

## Benefits

1. **Testability**: Can run `pytest` to test all logic
2. **Maintainability**: Clear module boundaries
3. **Reusability**: Modules can be used outside notebooks
4. **CI/CD**: Can add automated testing
5. **Debugging**: Easier to debug pure Python functions
6. **IDE Support**: Better autocomplete and type checking
