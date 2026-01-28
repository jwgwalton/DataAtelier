"""Test suite for policy management."""

import pytest
import tempfile
import os
from dataatelier import policy
from dataatelier.models import FewShotExample


def test_load_policy():
    """Test policy loading."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Test Policy\n\nThis is a test policy.")
        f.flush()
        
        content = policy.load_policy(f.name)
        assert "Test Policy" in content
        
        os.unlink(f.name)


def test_get_policy_version():
    """Test policy version calculation."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Test Policy")
        f.flush()
        
        version = policy.get_policy_version(f.name)
        assert len(version) == 8  # MD5 hash first 8 chars
        
        os.unlink(f.name)


def test_save_and_load_few_shot_examples():
    """Test few-shot example persistence."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.close()
        
        # Save examples
        example1 = FewShotExample(
            label="keep",
            reason="Important",
            excerpt="test content",
            path_hint="important.txt",
            content_type="text/plain",
            date="2024-01-01",
            reviewer="human"
        )
        
        example2 = FewShotExample(
            label="delete",
            reason="Temporary",
            excerpt="temp content",
            path_hint="tmp/temp.txt",
            content_type="text/plain",
            date="2024-01-01",
            reviewer="human"
        )
        
        policy.save_few_shot_example(f.name, example1)
        policy.save_few_shot_example(f.name, example2)
        
        # Load examples
        examples = policy.load_few_shot_examples(f.name, max_examples=10, balance=True)
        assert len(examples) == 2
        
        # Test balancing
        balanced = policy.load_few_shot_examples(f.name, max_examples=2, balance=True)
        labels = [e.label for e in balanced]
        assert 'keep' in labels
        assert 'delete' in labels
        
        os.unlink(f.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
