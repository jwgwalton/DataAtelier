"""Data models for DataAtelier."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class BlobMetadata:
    """Metadata for a blob in Azure Storage."""
    
    url: str
    container: str
    name: str
    path: str
    size: int
    last_modified: Optional[datetime]
    content_type: str
    etag: str
    preview: str = ""
    preview_length: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'url': self.url,
            'container': self.container,
            'name': self.name,
            'path': self.path,
            'size': self.size,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
            'content_type': self.content_type,
            'etag': self.etag,
            'preview': self.preview,
            'preview_length': self.preview_length,
        }


@dataclass
class TriageDecision:
    """Decision from LLM triage."""
    
    label: str  # 'keep', 'delete', or 'human_review'
    confidence: float
    reason: str
    policy_version: str = ""
    examples_version: str = ""
    
    def is_certain(self, threshold: float = 0.95) -> bool:
        """Check if decision meets confidence threshold."""
        return self.confidence >= threshold and self.label in ('keep', 'delete')


@dataclass
class QueueEntry:
    """Entry in a processing queue."""
    
    url: str
    container: str
    name: str
    decision: str
    reason: str
    source: str  # 'auto' or 'human'
    decided_at: str
    policy_version: str
    examples_version: str
    confidence: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'url': self.url,
            'container': self.container,
            'name': self.name,
            'decision': self.decision,
            'reason': self.reason,
            'source': self.source,
            'decided_at': self.decided_at,
            'policy_version': self.policy_version,
            'examples_version': self.examples_version,
            'confidence': self.confidence,
        }


@dataclass
class AuditEntry:
    """Entry in audit log."""
    
    timestamp: str
    blob_name: str
    action: str
    source: str
    reason: str
    metadata: str  # JSON string
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'blob_name': self.blob_name,
            'action': self.action,
            'source': self.source,
            'reason': self.reason,
            'metadata': self.metadata,
        }


@dataclass
class FewShotExample:
    """Few-shot learning example."""
    
    label: str
    reason: str
    excerpt: str
    path_hint: str
    content_type: str
    date: str
    reviewer: str
    cues: Optional[list[str]] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'label': self.label,
            'reason': self.reason,
            'excerpt': self.excerpt,
            'path_hint': self.path_hint,
            'content_type': self.content_type,
            'date': self.date,
            'reviewer': self.reviewer,
            'cues': self.cues or [],
        }
