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
from . import storage, extractors, policy, queue, audit, llm, triage, deletion
from .cleanup import BlobCleanup

# UI components (optional - only if ipywidgets is available)
try:
    from .ui import ReviewUI as ModularReviewUI, ProgressDisplay, create_progress_widget
    UI_AVAILABLE = True
except ImportError:
    UI_AVAILABLE = False
    ModularReviewUI = None
    ProgressDisplay = None
    create_progress_widget = None

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
    "BlobCleanup",
    "storage",
    "extractors",
    "policy",
    "queue",
    "audit",
    "llm",
    "triage",
    "deletion",
]

# Add UI components if available
if UI_AVAILABLE:
    __all__.extend(["ModularReviewUI", "ProgressDisplay", "create_progress_widget"])
