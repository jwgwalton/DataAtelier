"""Test suite for queue management."""

import pytest
import tempfile
import os
from pathlib import Path
from dataatelier.config import Config
from dataatelier.models import QueueEntry
from dataatelier import queue


def test_initialize_queues():
    """Test queue initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = {
            'to_review': os.path.join(tmpdir, 'to_review.csv'),
            'to_delete': os.path.join(tmpdir, 'to_delete.csv'),
            'to_keep': os.path.join(tmpdir, 'to_keep.csv'),
            'audit_log': os.path.join(tmpdir, 'audit_log.csv'),
            'few_shot': os.path.join(tmpdir, 'few_shot.jsonl'),
        }
        
        queue.initialize_queues(paths)
        
        assert os.path.exists(paths['to_review'])
        assert os.path.exists(paths['to_delete'])
        assert os.path.exists(paths['to_keep'])
        assert os.path.exists(paths['audit_log'])


def test_add_to_queue():
    """Test adding entries to queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_file = os.path.join(tmpdir, 'test_queue.csv')
        
        # Initialize
        import pandas as pd
        columns = ['url', 'container', 'name', 'decision', 'reason', 'source',
                   'decided_at', 'policy_version', 'examples_version', 'confidence']
        pd.DataFrame(columns=columns).to_csv(queue_file, index=False)
        
        # Add entry
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
        
        queue.add_to_queue(queue_file, entry)
        
        # Load and verify
        entries = queue.load_queue(queue_file)
        assert len(entries) == 1
        assert entries[0].name == "test.txt"


def test_remove_from_queue():
    """Test removing entries from queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_file = os.path.join(tmpdir, 'test_queue.csv')
        
        # Initialize with data
        import pandas as pd
        data = [{
            'url': 'https://test',
            'container': 'test',
            'name': 'test1.txt',
            'decision': 'keep',
            'reason': 'test',
            'source': 'human',
            'decided_at': '2024-01-01',
            'policy_version': 'v1',
            'examples_version': 'v1',
            'confidence': 1.0
        }, {
            'url': 'https://test',
            'container': 'test',
            'name': 'test2.txt',
            'decision': 'keep',
            'reason': 'test',
            'source': 'human',
            'decided_at': '2024-01-01',
            'policy_version': 'v1',
            'examples_version': 'v1',
            'confidence': 1.0
        }]
        pd.DataFrame(data).to_csv(queue_file, index=False)
        
        # Remove one
        queue.remove_from_queue(queue_file, 'test1.txt')
        
        # Verify
        entries = queue.load_queue(queue_file)
        assert len(entries) == 1
        assert entries[0].name == 'test2.txt'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
