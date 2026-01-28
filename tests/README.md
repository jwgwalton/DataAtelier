# Integration Tests

This directory contains integration tests for the DataAtelier Azure Blob Cleanup TUI application.

## Test Structure

- `conftest.py` - Pytest fixtures and mocks for Azure Blob Storage and LLM
- `test_integration.py` - Complete integration test suite

## Running Tests

### Install Test Dependencies

```bash
pip install -e ".[dev]"
```

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test Classes

```bash
# Test Azure Storage integration
pytest tests/test_integration.py::TestStorageIntegration -v

# Test LLM integration
pytest tests/test_integration.py::TestLLMIntegration -v

# Test state management
pytest tests/test_integration.py::TestStateManagement -v

# Test end-to-end workflow
pytest tests/test_integration.py::TestEndToEndWorkflow -v

# Test policy and examples
pytest tests/test_integration.py::TestPolicyAndExamples -v
```

### Run Single Test

```bash
pytest tests/test_integration.py::TestStorageIntegration::test_list_blobs -v
```

## Test Coverage

The test suite covers:

1. **Storage Integration** (5 tests)
   - Listing blobs from container
   - Filtering with prefix
   - Getting text previews
   - Text content detection
   - Blob deletion

2. **LLM Integration** (3 tests)
   - Classification for deletion
   - Classification for keeping
   - Batch classification

3. **State Management** (4 tests)
   - Writing and reading manifest
   - Adding items to queues
   - Moving items between queues
   - Coverage statistics

4. **End-to-End Workflow** (2 tests)
   - Full cleanup workflow with LLM
   - Manual workflow without LLM

5. **Policy and Examples** (2 tests)
   - Policy versioning
   - Few-shot examples management

6. **Example Scripts** (1 test)
   - Verifying example files exist

## Mocking Strategy

### Azure Blob Storage Mocks

The tests use custom mock classes to simulate Azure Blob Storage:

- `MockBlob` - Simulates blob objects with content
- `MockContainerClient` - Simulates container operations
- `MockBlobServiceClient` - Simulates the blob service

Sample blob data includes:
- Old log files (should be deleted)
- Important production files (should be kept)
- Binary files (require human review)

### LLM Mocks

The LLM is mocked with predefined responses based on blob names:

- Old logs → `delete` with high confidence
- Production configs → `keep` with high confidence
- Audit logs → `keep` with 100% confidence
- Unclear items → `human_review` with low confidence

This allows testing the entire workflow without actual API calls.

## Test Data

Test data is defined in `conftest.py`:

```python
sample_blobs = [
    "logs/app.log.2023.01.15",      # Old log - delete
    "logs/debug.log.old",            # Old debug - delete
    "cache/temp-session-123.tmp",    # Cache - delete
    "config/production.yaml",        # Config - keep
    "audit/audit.log",               # Audit - keep
    "prod/data/important.csv",       # Production - keep
    "images/logo.png",               # Binary - review
]
```

## Debugging Tests

### Verbose Output

```bash
pytest tests/ -v -s
```

### Show Warnings

```bash
pytest tests/ -v --tb=short
```

### Stop on First Failure

```bash
pytest tests/ -x
```

### Run with Coverage

```bash
pip install pytest-cov
pytest tests/ --cov=lib --cov-report=html
```

## Adding New Tests

1. Add fixtures to `conftest.py` if needed
2. Create test class or function in `test_integration.py`
3. Use descriptive test names: `test_<what>_<expected_behavior>`
4. Include docstring explaining the test
5. Run the test to verify it works

Example:

```python
def test_new_feature(mock_state_manager):
    """Test that new feature works correctly."""
    # Setup
    ...
    
    # Execute
    result = function_under_test()
    
    # Verify
    assert result == expected_value
```

## CI/CD

These tests are designed to run in CI/CD pipelines without any external dependencies:
- No real Azure Storage required
- No OpenAI API key required
- All mocked for fast, reliable execution

## Notes

- Tests use temporary directories (`tmp_path` fixture) for state files
- All file I/O is done in temp directories
- Mocks are reset between tests automatically
- Tests run in ~1-2 seconds total
