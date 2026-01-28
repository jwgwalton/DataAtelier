"""Test suite for DataAtelier modules."""

import pytest
import os
import tempfile
from dataatelier.config import Config
from dataatelier.models import BlobMetadata, TriageDecision, QueueEntry, AuditEntry, FewShotExample


def test_config_from_env():
    """Test configuration from environment variables."""
    config = Config(
        storage_connection_string="test_connection",
        container_name="test_container",
        llm_provider="openai",
        openai_api_key="test_key"
    )
    
    assert config.storage_connection_string == "test_connection"
    assert config.container_name == "test_container"
    assert config.llm_provider == "openai"
    assert config.openai_api_key == "test_key"


def test_config_validation():
    """Test configuration validation."""
    config = Config()
    errors = config.validate()
    
    # Should have errors for missing required fields
    assert len(errors) > 0
    assert any("AZURE_STORAGE_CONNECTION_STRING" in e for e in errors)


def test_blob_metadata():
    """Test BlobMetadata model."""
    from datetime import datetime
    
    blob = BlobMetadata(
        url="https://test.blob.core.windows.net/test",
        container="test",
        name="test.txt",
        path="test.txt",
        size=100,
        last_modified=datetime.now(),
        content_type="text/plain",
        etag="test_etag",
        preview="test content",
        preview_length=12
    )
    
    data = blob.to_dict()
    assert data['name'] == "test.txt"
    assert data['size'] == 100


def test_triage_decision():
    """Test TriageDecision model."""
    decision = TriageDecision(
        label="keep",
        confidence=0.98,
        reason="Important file",
        policy_version="v1",
        examples_version="v1"
    )
    
    assert decision.is_certain(threshold=0.95)
    assert decision.label == "keep"


def test_queue_entry():
    """Test QueueEntry model."""
    entry = QueueEntry(
        url="https://test",
        container="test",
        name="test.txt",
        decision="keep",
        reason="test",
        source="human",
        decided_at="2024-01-01",
        policy_version="v1",
        examples_version="v1",
        confidence=1.0
    )
    
    data = entry.to_dict()
    assert data['source'] == "human"
    assert data['confidence'] == 1.0


def test_audit_entry():
    """Test AuditEntry model."""
    entry = AuditEntry(
        timestamp="2024-01-01T00:00:00",
        blob_name="test.txt",
        action="keep",
        source="human",
        reason="Important",
        metadata="{}"
    )
    
    data = entry.to_dict()
    assert data['action'] == "keep"


def test_few_shot_example():
    """Test FewShotExample model."""
    example = FewShotExample(
        label="delete",
        reason="Temporary file",
        excerpt="temp content",
        path_hint="tmp/test.txt",
        content_type="text/plain",
        date="2024-01-01",
        reviewer="human"
    )
    
    data = example.to_dict()
    assert data['label'] == "delete"
    assert 'cues' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
