"""Tests for cleanup.py and ui.py modules."""

import json
import pytest
from pathlib import Path
from datetime import datetime
import pandas as pd
import tempfile
import shutil

from dataatelier.cleanup import BlobCleanup
from dataatelier.config import Config
from dataatelier.models import BlobMetadata, QueueEntry
from dataatelier.queue import initialize_queues, add_to_queue, get_statistics
from dataatelier.llm import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Mock LLM client for testing."""
    
    def __init__(self, response=None):
        self.response = response or {
            'label': 'delete',
            'confidence': 0.98,
            'reason': 'Test file - not needed'
        }
    
    def call(self, prompt: str, temperature: float = 0.0) -> str:
        """Return mock response."""
        return json.dumps(self.response)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def test_config(temp_dir):
    """Create test configuration."""
    config = Config(
        storage_connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=test==;EndpointSuffix=core.windows.net",
        container_name="test-container",
        llm_provider="openai",
        openai_api_key="test-key",
        confidence_threshold=0.95,
        self_consistency_runs=3,
        batch_size=10
    )
    
    # Override file paths to temp directory
    config.manifest_file = str(Path(temp_dir) / "manifest.csv")
    config.to_keep_file = str(Path(temp_dir) / "to_keep.csv")
    config.to_delete_file = str(Path(temp_dir) / "to_delete.csv")
    config.to_review_file = str(Path(temp_dir) / "to_review.csv")
    config.audit_log_file = str(Path(temp_dir) / "audit_log.csv")
    config.policy_file = str(Path(temp_dir) / "llm_policy.md")
    config.few_shot_file = str(Path(temp_dir) / "few_shot_examples.jsonl")
    
    # Create policy file
    Path(config.policy_file).write_text("# Test Policy\n\nDelete temporary files.")
    
    return config


def test_blob_cleanup_init(test_config):
    """Test BlobCleanup initialization."""
    cleanup = BlobCleanup(test_config)
    
    assert cleanup.config == test_config
    assert cleanup.container_client is None  # Lazy initialization
    assert cleanup.llm_client is None  # Lazy initialization
    
    # Check that queues were initialized
    assert Path(test_config.to_keep_file).exists()
    assert Path(test_config.to_delete_file).exists()
    assert Path(test_config.to_review_file).exists()


def test_blob_cleanup_init_invalid_config():
    """Test BlobCleanup initialization with invalid config."""
    config = Config()  # Missing required fields
    
    with pytest.raises(ValueError) as exc_info:
        BlobCleanup(config)
    
    assert "Configuration errors" in str(exc_info.value)


def test_show_progress(test_config):
    """Test show_progress method."""
    cleanup = BlobCleanup(test_config)
    
    # Create a simple manifest
    manifest_data = [
        {
            'url': 'https://test.blob.core.windows.net/container/file1.txt',
            'container': 'test-container',
            'name': 'file1.txt',
            'path': 'file1.txt',
            'size': 1024,
            'last_modified': datetime.utcnow().isoformat(),
            'content_type': 'text/plain',
            'etag': 'abc123',
            'preview': 'Test content',
            'preview_length': 12
        }
    ]
    manifest_df = pd.DataFrame(manifest_data)
    manifest_df.to_csv(test_config.manifest_file, index=False)
    
    # Add entry to to_keep queue
    entry = QueueEntry(
        url='https://test.blob.core.windows.net/container/file1.txt',
        container='test-container',
        name='file1.txt',
        decision='keep',
        reason='Important file',
        source='human',
        decided_at=datetime.utcnow().isoformat(),
        policy_version='v1',
        examples_version='v1',
        confidence=1.0
    )
    add_to_queue(test_config.to_keep_file, entry)
    
    # Get progress
    stats = cleanup.show_progress()
    
    assert stats['total_blobs'] == 1
    assert stats['labeled'] == 1
    assert stats['unlabeled'] == 0
    assert stats['to_keep'] == 1
    assert stats['to_delete'] == 0
    assert stats['to_review'] == 0


def test_get_unlabeled_count(test_config):
    """Test get_unlabeled_count method."""
    cleanup = BlobCleanup(test_config)
    
    # Create manifest with 3 blobs
    manifest_data = []
    for i in range(3):
        manifest_data.append({
            'url': f'https://test.blob.core.windows.net/container/file{i}.txt',
            'container': 'test-container',
            'name': f'file{i}.txt',
            'path': f'file{i}.txt',
            'size': 1024,
            'last_modified': datetime.utcnow().isoformat(),
            'content_type': 'text/plain',
            'etag': f'abc{i}',
            'preview': f'Test content {i}',
            'preview_length': 14
        })
    manifest_df = pd.DataFrame(manifest_data)
    manifest_df.to_csv(test_config.manifest_file, index=False)
    
    # Label one blob
    entry = QueueEntry(
        url='https://test.blob.core.windows.net/container/file0.txt',
        container='test-container',
        name='file0.txt',
        decision='keep',
        reason='Important',
        source='human',
        decided_at=datetime.utcnow().isoformat(),
        policy_version='v1',
        examples_version='v1',
        confidence=1.0
    )
    add_to_queue(test_config.to_keep_file, entry)
    
    # Check unlabeled count
    unlabeled_count = cleanup.get_unlabeled_count()
    assert unlabeled_count == 2


def test_archive_artifacts(test_config, temp_dir):
    """Test archive_artifacts method."""
    cleanup = BlobCleanup(test_config)
    
    # Create some artifacts
    manifest_data = [{
        'url': 'https://test.blob.core.windows.net/container/file1.txt',
        'container': 'test-container',
        'name': 'file1.txt',
        'path': 'file1.txt',
        'size': 1024,
        'last_modified': datetime.utcnow().isoformat(),
        'content_type': 'text/plain',
        'etag': 'abc123',
        'preview': 'Test',
        'preview_length': 4
    }]
    manifest_df = pd.DataFrame(manifest_data)
    manifest_df.to_csv(test_config.manifest_file, index=False)
    
    # Archive
    archive_dir = str(Path(temp_dir) / "archives")
    archive_path = cleanup.archive_artifacts(archive_dir)
    
    # Check that archive was created
    assert Path(archive_path).exists()
    assert Path(archive_path).is_dir()
    
    # Check that files were archived
    archived_manifest = Path(archive_path) / "manifest.csv"
    assert archived_manifest.exists()
    
    # Check metadata
    metadata_file = Path(archive_path) / "archive_metadata.json"
    assert metadata_file.exists()
    
    with metadata_file.open() as f:
        metadata = json.load(f)
        assert 'timestamp' in metadata
        assert 'archived_files' in metadata
        assert 'statistics' in metadata


def test_get_next_review_item(test_config):
    """Test get_next_review_item method."""
    cleanup = BlobCleanup(test_config)
    
    # Create manifest
    manifest_data = [{
        'url': 'https://test.blob.core.windows.net/container/file1.txt',
        'container': 'test-container',
        'name': 'file1.txt',
        'path': 'folder/file1.txt',
        'size': 2048,
        'last_modified': datetime.utcnow().isoformat(),
        'content_type': 'text/plain',
        'etag': 'abc123',
        'preview': 'Review this content',
        'preview_length': 19
    }]
    manifest_df = pd.DataFrame(manifest_data)
    manifest_df.to_csv(test_config.manifest_file, index=False)
    
    # Add to review queue
    entry = QueueEntry(
        url='https://test.blob.core.windows.net/container/file1.txt',
        container='test-container',
        name='file1.txt',
        decision='human_review',
        reason='Needs review',
        source='auto',
        decided_at=datetime.utcnow().isoformat(),
        policy_version='v1',
        examples_version='v1',
        confidence=0.5
    )
    add_to_queue(test_config.to_review_file, entry)
    
    # Get next item
    item = cleanup.get_next_review_item()
    
    assert item is not None
    assert item['name'] == 'file1.txt'
    assert item['path'] == 'folder/file1.txt'
    assert item['size'] == 2048
    assert item['preview'] == 'Review this content'
    assert item['confidence'] == 0.5
    
    # Test when queue is empty (after removing the item)
    from dataatelier.queue import remove_from_queue
    remove_from_queue(test_config.to_review_file, 'file1.txt')
    
    item = cleanup.get_next_review_item()
    assert item is None


def test_ui_imports():
    """Test that UI components can be imported."""
    try:
        from dataatelier.ui import ReviewUI, ProgressDisplay, create_progress_widget
        assert ReviewUI is not None
        assert ProgressDisplay is not None
        assert create_progress_widget is not None
    except ImportError:
        pytest.skip("ipywidgets not available")


def test_review_ui_initialization(test_config):
    """Test ReviewUI initialization."""
    try:
        from dataatelier.ui import ReviewUI
        
        ui = ReviewUI(test_config)
        assert ui.config == test_config
        assert ui.current_item is None
        assert ui.current_index == 0
        
    except ImportError:
        pytest.skip("ipywidgets not available")


def test_progress_display_initialization(test_config):
    """Test ProgressDisplay initialization."""
    try:
        from dataatelier.ui import ProgressDisplay
        
        display = ProgressDisplay(test_config)
        assert display.config == test_config
        
    except ImportError:
        pytest.skip("ipywidgets not available")


def test_create_progress_widget(test_config):
    """Test create_progress_widget function."""
    try:
        from dataatelier.ui import create_progress_widget
        
        # Create some test data
        manifest_data = [{
            'url': 'https://test.blob.core.windows.net/container/file1.txt',
            'container': 'test-container',
            'name': 'file1.txt',
            'path': 'file1.txt',
            'size': 1024,
            'last_modified': datetime.utcnow().isoformat(),
            'content_type': 'text/plain',
            'etag': 'abc',
            'preview': 'Test',
            'preview_length': 4
        }]
        manifest_df = pd.DataFrame(manifest_data)
        manifest_df.to_csv(test_config.manifest_file, index=False)
        
        widget = create_progress_widget(test_config)
        assert widget is not None
        
    except ImportError:
        pytest.skip("ipywidgets not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
