"""DataAtelier - Human-in-the-Loop Data Cleansing with LLM Assistance."""

__version__ = "0.1.0"

from .blob_cleanup import (
    BlobCleanupConfig,
    BlobMetadata,
    TriageDecision,
    BlobInventory,
    LLMTriageEngine,
    QueueManager,
    ReviewUI,
    DeletionManager,
    AzureBlobCleanup,
    create_cleanup_tool,
    quick_start,
)

# New modular components
from .config import Config
from .models import QueueEntry, AuditEntry, FewShotExample
from . import storage, extractors, policy, queue, audit

__all__ = [
    # Legacy blob_cleanup exports
    "BlobCleanupConfig",
    "BlobMetadata",
    "TriageDecision",
    "BlobInventory",
    "LLMTriageEngine",
    "QueueManager",
    "ReviewUI",
    "DeletionManager",
    "AzureBlobCleanup",
    "create_cleanup_tool",
    "quick_start",
    # New modular components
    "Config",
    "QueueEntry",
    "AuditEntry",
    "FewShotExample",
    "storage",
    "extractors",
    "policy",
    "queue",
    "audit",
]
