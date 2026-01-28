"""
Pytest configuration and fixtures for DataAtelier tests.

This module provides fixtures for mocking Azure Blob Storage and LLM responses.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import MagicMock, Mock

import pytest


# Mock Blob Data
class MockBlob:
    """Mock Azure Blob object."""
    
    def __init__(self, name: str, size: int, content: str = "", content_type: str = "text/plain"):
        self.name = name
        self.size = size
        self.content_type = content_type
        self.last_modified = datetime.utcnow() - timedelta(days=30)
        self._content = content.encode() if content else b""
    
    def download_blob(self, max_concurrency=1, length=None):
        """Mock download_blob method."""
        mock_stream = Mock()
        if length:
            mock_stream.readall = Mock(return_value=self._content[:length])
        else:
            mock_stream.readall = Mock(return_value=self._content)
        return mock_stream


class MockContainerClient:
    """Mock Azure Container Client."""
    
    def __init__(self, container_name: str, blobs: List[MockBlob]):
        self.container_name = container_name
        self.url = f"https://mockaccount.blob.core.windows.net/{container_name}"
        self._blobs = blobs
        self._deleted_blobs = []
    
    def list_blobs(self, name_starts_with=None):
        """Mock list_blobs method."""
        blobs = self._blobs
        if name_starts_with:
            blobs = [b for b in blobs if b.name.startswith(name_starts_with)]
        return blobs
    
    def get_blob_client(self, blob_name: str):
        """Mock get_blob_client method."""
        blob = next((b for b in self._blobs if b.name == blob_name), None)
        if blob:
            mock_client = Mock()
            mock_client.download_blob = blob.download_blob
            mock_client.delete_blob = Mock(side_effect=lambda **kwargs: self._delete_blob(blob_name))
            return mock_client
        else:
            # Return a mock that raises ResourceNotFoundError
            from azure.core.exceptions import ResourceNotFoundError
            mock_client = Mock()
            mock_client.download_blob = Mock(side_effect=ResourceNotFoundError("Blob not found"))
            mock_client.delete_blob = Mock(side_effect=ResourceNotFoundError("Blob not found"))
            return mock_client
    
    def _delete_blob(self, blob_name: str):
        """Internal method to track deleted blobs."""
        self._deleted_blobs.append(blob_name)
        # Remove from blobs list
        self._blobs = [b for b in self._blobs if b.name != blob_name]


@pytest.fixture
def sample_blobs():
    """Create sample blob data for testing."""
    return [
        # Old log files - should be deleted
        MockBlob(
            name="logs/app.log.2023.01.15",
            size=1024 * 100,  # 100KB
            content="2023-01-15 INFO Application started\n2023-01-15 INFO Processing...",
            content_type="text/plain"
        ),
        MockBlob(
            name="logs/debug.log.old",
            size=1024 * 50,
            content="DEBUG: temp file for testing",
            content_type="text/plain"
        ),
        MockBlob(
            name="cache/temp-session-123.tmp",
            size=512,
            content="temporary session data",
            content_type="text/plain"
        ),
        
        # Important files - should be kept
        MockBlob(
            name="config/production.yaml",
            size=2048,
            content="database:\n  host: prod-db\n  port: 5432",
            content_type="application/x-yaml"
        ),
        MockBlob(
            name="audit/audit.log",
            size=1024 * 200,
            content="2026-01-28 AUDIT: User login successful",
            content_type="text/plain"
        ),
        MockBlob(
            name="prod/data/important.csv",
            size=1024 * 1024,  # 1MB
            content="id,name,value\n1,test,123",
            content_type="text/csv"
        ),
        
        # Binary file
        MockBlob(
            name="images/logo.png",
            size=1024 * 20,
            content="",  # Binary, no text content
            content_type="image/png"
        ),
    ]


@pytest.fixture
def mock_container_client(sample_blobs):
    """Create a mock Azure Container Client."""
    return MockContainerClient("test-container", sample_blobs)


@pytest.fixture
def mock_blob_service_client(mock_container_client):
    """Create a mock Azure Blob Service Client."""
    mock_service = Mock()
    mock_service.get_container_client = Mock(return_value=mock_container_client)
    return mock_service


@pytest.fixture
def mock_storage_io(mock_blob_service_client, monkeypatch):
    """Create a mock StorageIO instance."""
    from lib.storage_io import StorageIO
    
    # Patch the BlobServiceClient constructor
    def mock_init(self, connection_string=None, account_url=None, sas_token=None):
        self.blob_service_client = mock_blob_service_client
    
    monkeypatch.setattr(StorageIO, "__init__", mock_init)
    
    storage = StorageIO(connection_string="mock_connection_string")
    return storage


@pytest.fixture
def mock_llm_responses():
    """Mock LLM responses for classification."""
    return {
        # Old logs - delete
        "logs/app.log.2023.01.15": {
            "label": "delete",
            "confidence": 0.98,
            "reason": "Old rotated log file from 2023, beyond retention period"
        },
        "logs/debug.log.old": {
            "label": "delete",
            "confidence": 0.97,
            "reason": "Old debug log marked as .old, safe to delete"
        },
        "cache/temp-session-123.tmp": {
            "label": "delete",
            "confidence": 0.99,
            "reason": "Temporary cache file, can be safely deleted"
        },
        
        # Important files - keep
        "config/production.yaml": {
            "label": "keep",
            "confidence": 0.99,
            "reason": "Production configuration file, must be preserved"
        },
        "audit/audit.log": {
            "label": "keep",
            "confidence": 1.0,
            "reason": "Audit log - required for compliance, never delete"
        },
        "prod/data/important.csv": {
            "label": "keep",
            "confidence": 0.98,
            "reason": "Production data file, must be preserved"
        },
        
        # Uncertain - human review
        "images/logo.png": {
            "label": "human_review",
            "confidence": 0.75,
            "reason": "Binary image file, unclear if still needed"
        }
    }


@pytest.fixture
def mock_llm_client(mock_llm_responses, monkeypatch):
    """Mock OpenAI client for testing."""
    
    class MockCompletions:
        def create(self, **kwargs):
            """Mock chat.completions.create method."""
            messages = kwargs.get("messages", [])
            
            # Extract blob name from the user message
            user_message = next((m["content"] for m in messages if m["role"] == "user"), "")
            
            # Find matching response
            response = None
            for blob_name, llm_response in mock_llm_responses.items():
                if blob_name in user_message:
                    response = llm_response
                    break
            
            # Default to human_review if no match
            if not response:
                response = {
                    "label": "human_review",
                    "confidence": 0.5,
                    "reason": "Unable to classify with confidence"
                }
            
            # Create mock response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.content = json.dumps(response)
            
            return mock_response
    
    # Patch the OpenAI client
    mock_client = Mock()
    mock_client.chat = Mock()
    mock_client.chat.completions = MockCompletions()
    
    return mock_client


@pytest.fixture
def mock_triage_llm(mock_llm_client, monkeypatch):
    """Create a mock TriageLLM instance."""
    from lib.triage_llm import TriageLLM
    
    # Patch the client initialization
    def mock_init(
        self,
        model="gpt-4",
        confidence_threshold=0.95,
        self_consistency_passes=3,
        temperature=0.0,
        use_azure=False,
    ):
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.self_consistency_passes = self_consistency_passes
        self.temperature = temperature
        self.client = mock_llm_client
        self.system_prompt = "Mock system prompt"
    
    monkeypatch.setattr(TriageLLM, "__init__", mock_init)
    
    llm = TriageLLM()
    return llm


@pytest.fixture
def temp_work_dir(tmp_path):
    """Create a temporary work directory for tests."""
    return tmp_path


@pytest.fixture
def mock_state_manager(temp_work_dir):
    """Create a StateManager instance with temp directory."""
    from lib.state import StateManager
    return StateManager(work_dir=str(temp_work_dir))
