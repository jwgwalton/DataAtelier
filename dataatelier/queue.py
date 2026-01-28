"""Queue management for DataAtelier."""

import csv
from pathlib import Path
from typing import Optional
import pandas as pd

from .models import QueueEntry


# CSV field names for queue files
QUEUE_FIELDS = [
    'url',
    'container',
    'name',
    'decision',
    'reason',
    'source',
    'decided_at',
    'policy_version',
    'examples_version',
    'confidence'
]


def initialize_queues(queue_paths: list[str]) -> None:
    """Initialize queue CSV files if they don't exist.
    
    Creates empty CSV files with headers for all specified queue paths.
    
    Args:
        queue_paths: List of paths to queue CSV files
        
    Raises:
        IOError: If files cannot be created
    """
    for file_path in queue_paths:
        path = Path(file_path)
        
        if path.exists():
            continue
        
        try:
            # Create parent directory if it doesn't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create CSV with header
            with path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
                writer.writeheader()
                
        except Exception as e:
            raise IOError(f"Failed to initialize queue '{file_path}': {e}") from e


def load_queue(file_path: str) -> list[QueueEntry]:
    """Load queue entries from CSV file.
    
    Args:
        file_path: Path to queue CSV file
        
    Returns:
        List of QueueEntry objects
        
    Raises:
        FileNotFoundError: If queue file doesn't exist
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
                entry = QueueEntry(
                    url=row['url'],
                    container=row['container'],
                    name=row['name'],
                    decision=row['decision'],
                    reason=row['reason'],
                    source=row['source'],
                    decided_at=row['decided_at'],
                    policy_version=row['policy_version'],
                    examples_version=row['examples_version'],
                    confidence=float(row['confidence']),
                )
                entries.append(entry)
        
        return entries
        
    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise IOError(f"Failed to load queue from '{file_path}': {e}") from e


def save_queue(file_path: str, entries: list[QueueEntry]) -> None:
    """Save queue entries to CSV file.
    
    Overwrites the existing file with the provided entries.
    
    Args:
        file_path: Path to queue CSV file
        entries: List of QueueEntry objects to save
        
    Raises:
        IOError: If file cannot be written
    """
    path = Path(file_path)
    
    try:
        # Create parent directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
            writer.writeheader()
            
            for entry in entries:
                writer.writerow(entry.to_dict())
                
    except Exception as e:
        raise IOError(f"Failed to save queue to '{file_path}': {e}") from e


def add_to_queue(file_path: str, entry: QueueEntry) -> None:
    """Add an entry to a queue CSV file.
    
    Appends the entry to the file without reading existing entries.
    
    Args:
        file_path: Path to queue CSV file
        entry: QueueEntry to add
        
    Raises:
        IOError: If file cannot be written
    """
    path = Path(file_path)
    
    try:
        # Create file with header if it doesn't exist
        if not path.exists():
            initialize_queues([file_path])
        
        # Append entry
        with path.open('a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
            writer.writerow(entry.to_dict())
            
    except Exception as e:
        raise IOError(f"Failed to add entry to queue '{file_path}': {e}") from e


def remove_from_queue(file_path: str, blob_name: str) -> None:
    """Remove an entry from a queue by blob name.
    
    Loads all entries, filters out the specified blob, and saves back.
    
    Args:
        file_path: Path to queue CSV file
        blob_name: Name of the blob to remove
        
    Raises:
        IOError: If file cannot be read or written
    """
    entries = load_queue(file_path)
    filtered_entries = [e for e in entries if e.name != blob_name]
    save_queue(file_path, filtered_entries)


def get_unlabeled_blobs(manifest_path: str, queue_paths: list[str]) -> pd.DataFrame:
    """Get blobs that haven't been labeled yet.
    
    Compares the manifest with all queue files to find unlabeled blobs.
    
    Args:
        manifest_path: Path to manifest CSV file
        queue_paths: List of paths to queue CSV files
        
    Returns:
        DataFrame of unlabeled blobs
        
    Raises:
        FileNotFoundError: If manifest file doesn't exist
        IOError: If files cannot be read
    """
    manifest_path_obj = Path(manifest_path)
    
    if not manifest_path_obj.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    
    try:
        # Load manifest
        manifest_df = pd.read_csv(manifest_path)
        
        if manifest_df.empty:
            return pd.DataFrame()
        
        # Collect all labeled blob names from queues
        labeled_names = set()
        
        for queue_path in queue_paths:
            queue_path_obj = Path(queue_path)
            if queue_path_obj.exists():
                queue_df = pd.read_csv(queue_path)
                if not queue_df.empty and 'name' in queue_df.columns:
                    labeled_names.update(queue_df['name'].tolist())
        
        # Filter manifest to get unlabeled blobs
        if 'name' not in manifest_df.columns:
            return pd.DataFrame()
        
        unlabeled_df = manifest_df[~manifest_df['name'].isin(labeled_names)]
        return unlabeled_df
        
    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise IOError(f"Failed to get unlabeled blobs: {e}") from e


def get_statistics(config) -> dict:
    """Get statistics about queues and processing status.
    
    Args:
        config: Config object or dict with file paths
                (manifest_file, to_keep_file, to_delete_file, to_review_file)
        
    Returns:
        Dictionary with statistics
    """
    # Support both Config object and dict
    if hasattr(config, 'manifest_file'):
        manifest_path = config.manifest_file
        to_keep_path = config.to_keep_file
        to_delete_path = config.to_delete_file
        to_review_path = config.to_review_file
    else:
        manifest_path = config.get('manifest_file', 'manifest.csv')
        to_keep_path = config.get('to_keep_file', 'to_keep.csv')
        to_delete_path = config.get('to_delete_file', 'to_delete.csv')
        to_review_path = config.get('to_review_file', 'to_review.csv')
    
    stats = {
        'total_blobs': 0,
        'to_keep': 0,
        'to_delete': 0,
        'to_review': 0,
        'unlabeled': 0,
        'labeled': 0,
        'auto_labeled': 0,
        'human_labeled': 0,
    }
    
    try:
        # Count total blobs
        manifest_path_obj = Path(manifest_path)
        if manifest_path_obj.exists():
            manifest_df = pd.read_csv(manifest_path)
            stats['total_blobs'] = len(manifest_df)
        
        # Count queues
        queue_paths = {
            'to_keep': to_keep_path,
            'to_delete': to_delete_path,
            'to_review': to_review_path,
        }
        
        auto_count = 0
        human_count = 0
        
        for queue_name, queue_path in queue_paths.items():
            queue_path_obj = Path(queue_path)
            if queue_path_obj.exists():
                queue_df = pd.read_csv(queue_path)
                count = len(queue_df)
                stats[queue_name] = count
                
                # Count by source
                if not queue_df.empty and 'source' in queue_df.columns:
                    auto_count += (queue_df['source'] == 'auto').sum()
                    human_count += (queue_df['source'] == 'human').sum()
        
        stats['labeled'] = stats['to_keep'] + stats['to_delete'] + stats['to_review']
        stats['unlabeled'] = stats['total_blobs'] - stats['labeled']
        stats['auto_labeled'] = auto_count
        stats['human_labeled'] = human_count
        
    except Exception:
        # Return default stats if there's an error
        pass
    
    return stats
