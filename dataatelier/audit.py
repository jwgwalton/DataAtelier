"""Audit logging for DataAtelier."""

import csv
from pathlib import Path
from typing import Optional

from .models import AuditEntry


# CSV field names for audit log
AUDIT_FIELDS = [
    'timestamp',
    'blob_name',
    'action',
    'source',
    'reason',
    'metadata'
]


def log_audit(file_path: str, entry: AuditEntry) -> None:
    """Append an audit entry to the audit log CSV file.
    
    Creates the file with headers if it doesn't exist.
    
    Args:
        file_path: Path to audit log CSV file
        entry: AuditEntry to log
        
    Raises:
        IOError: If file cannot be written
    """
    path = Path(file_path)
    
    try:
        # Create parent directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file exists to determine if we need to write header
        file_exists = path.exists()
        
        # Append entry
        with path.open('a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
            
            # Write header if new file
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(entry.to_dict())
            
    except Exception as e:
        raise IOError(f"Failed to log audit entry to '{file_path}': {e}") from e


def load_audit_log(
    file_path: str,
    blob_name: Optional[str] = None,
    action: Optional[str] = None
) -> list[AuditEntry]:
    """Load audit entries from CSV file.
    
    Args:
        file_path: Path to audit log CSV file
        blob_name: Optional filter by blob name
        action: Optional filter by action
        
    Returns:
        List of AuditEntry objects
        
    Raises:
        FileNotFoundError: If audit log file doesn't exist
        IOError: If file cannot be read
    """
    path = Path(file_path)
    
    if not path.exists():
        return []
    
    try:
        entries = []
        
        with path.open('r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Apply filters
                if blob_name and row['blob_name'] != blob_name:
                    continue
                if action and row['action'] != action:
                    continue
                
                entry = AuditEntry(
                    timestamp=row['timestamp'],
                    blob_name=row['blob_name'],
                    action=row['action'],
                    source=row['source'],
                    reason=row['reason'],
                    metadata=row['metadata'],
                )
                entries.append(entry)
        
        return entries
        
    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise IOError(f"Failed to load audit log from '{file_path}': {e}") from e
