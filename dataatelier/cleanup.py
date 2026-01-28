"""Main orchestrator for DataAtelier blob cleanup operations.

This module provides the BlobCleanup class which coordinates all other modules
to provide a high-level interface for blob storage cleanup with LLM-based triage.

NO Jupyter dependencies - pure Python only.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

from .config import Config
from .models import BlobMetadata, QueueEntry, AuditEntry
from .storage import get_container_client, list_blobs, download_blob_content
from .extractors import extract_text_preview
from .llm import create_llm_client, BaseLLMClient
from .triage import triage_blob, batch_triage
from .queue import (
    initialize_queues,
    add_to_queue,
    get_unlabeled_blobs,
    get_statistics,
    load_queue
)
from .audit import log_audit
from .policy import load_policy, load_few_shot_examples, get_policy_version, get_examples_version


class BlobCleanup:
    """Main orchestrator class for blob cleanup operations.
    
    Coordinates all modules to provide high-level workflow orchestration
    with stateful session management.
    """
    
    def __init__(self, config: Config):
        """Initialize BlobCleanup orchestrator.
        
        Args:
            config: Configuration object with all settings
            
        Raises:
            ValueError: If configuration is invalid
        """
        # Validate configuration
        errors = config.validate()
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        self.config = config
        self.container_client = None
        self.llm_client: Optional[BaseLLMClient] = None
        
        # Initialize queues
        queue_paths = [
            config.to_keep_file,
            config.to_delete_file,
            config.to_review_file
        ]
        initialize_queues(queue_paths)
        
        # Initialize audit log
        if not Path(config.audit_log_file).exists():
            Path(config.audit_log_file).parent.mkdir(parents=True, exist_ok=True)
    
    def _get_container_client(self):
        """Get or create container client (lazy initialization)."""
        if self.container_client is None:
            self.container_client = get_container_client(self.config)
        return self.container_client
    
    def _get_llm_client(self) -> BaseLLMClient:
        """Get or create LLM client (lazy initialization)."""
        if self.llm_client is None:
            self.llm_client = create_llm_client(self.config)
        return self.llm_client
    
    def create_manifest(self) -> pd.DataFrame:
        """Create manifest of all blobs in the container.
        
        Lists all blobs, downloads previews, and saves to manifest CSV.
        
        Returns:
            DataFrame containing blob manifest
            
        Raises:
            Exception: If listing blobs or creating manifest fails
        """
        try:
            # List all blobs
            blobs = list_blobs(self.config)
            
            # Limit if max_files is set
            if self.config.max_files > 0:
                blobs = blobs[:self.config.max_files]
            
            # Download previews for each blob
            manifest_data = []
            max_preview_bytes = self.config.preview_size_kb * 1024
            
            for blob in blobs:
                try:
                    # Download preview
                    content = download_blob_content(
                        self.config,
                        blob.name,
                        max_bytes=max_preview_bytes
                    )
                    
                    # Extract text preview
                    preview = extract_text_preview(
                        content,
                        blob.content_type,
                        max_preview_bytes
                    )
                    
                    blob.preview = preview
                    blob.preview_length = len(preview)
                    
                except Exception as e:
                    # If preview fails, log but continue
                    blob.preview = f"[Preview failed: {str(e)}]"
                    blob.preview_length = 0
                
                manifest_data.append(blob.to_dict())
            
            # Create DataFrame
            manifest_df = pd.DataFrame(manifest_data)
            
            # Save to CSV
            manifest_path = Path(self.config.manifest_file)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_df.to_csv(manifest_path, index=False)
            
            # Log audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.utcnow().isoformat(),
                blob_name='manifest',
                action='manifest_created',
                source='system',
                reason=f'Created manifest with {len(manifest_df)} blobs',
                metadata=json.dumps({'blob_count': len(manifest_df)})
            )
            log_audit(self.config.audit_log_file, audit_entry)
            
            return manifest_df
            
        except Exception as e:
            raise Exception(f"Failed to create manifest: {e}") from e
    
    def run_triage_batch(self, batch_size: Optional[int] = None) -> dict:
        """Run LLM triage on a batch of unlabeled blobs.
        
        Args:
            batch_size: Number of blobs to process (uses config default if None)
            
        Returns:
            Dictionary with statistics:
            - processed: Number of blobs processed
            - to_keep: Number labeled as keep
            - to_delete: Number labeled as delete
            - to_review: Number sent for human review
            
        Raises:
            FileNotFoundError: If manifest doesn't exist
            Exception: If triage fails
        """
        if batch_size is None:
            batch_size = self.config.batch_size
        
        try:
            # Get unlabeled blobs
            queue_paths = [
                self.config.to_keep_file,
                self.config.to_delete_file,
                self.config.to_review_file
            ]
            
            unlabeled_df = get_unlabeled_blobs(
                self.config.manifest_file,
                queue_paths
            )
            
            if unlabeled_df.empty:
                return {
                    'processed': 0,
                    'to_keep': 0,
                    'to_delete': 0,
                    'to_review': 0
                }
            
            # Take batch
            batch_df = unlabeled_df.head(batch_size)
            
            # Convert to BlobMetadata objects
            blobs = []
            for _, row in batch_df.iterrows():
                blob = BlobMetadata(
                    url=row.get('url', ''),
                    container=row.get('container', self.config.container_name),
                    name=row['name'],
                    path=row.get('path', row['name']),
                    size=int(row.get('size', 0)),
                    last_modified=row.get('last_modified'),
                    content_type=row.get('content_type', 'application/octet-stream'),
                    etag=row.get('etag', ''),
                    preview=row.get('preview', ''),
                    preview_length=int(row.get('preview_length', 0))
                )
                blobs.append(blob)
            
            # Get LLM client
            llm_client = self._get_llm_client()
            
            # Run triage
            decisions = batch_triage(self.config, blobs, llm_client)
            
            # Collect statistics
            stats = {
                'processed': len(decisions),
                'to_keep': 0,
                'to_delete': 0,
                'to_review': 0
            }
            
            # Add to queues
            timestamp = datetime.utcnow().isoformat()
            
            for blob, decision in zip(blobs, decisions):
                # Determine queue file
                if decision.label == 'keep':
                    queue_file = self.config.to_keep_file
                    stats['to_keep'] += 1
                elif decision.label == 'delete':
                    queue_file = self.config.to_delete_file
                    stats['to_delete'] += 1
                else:  # human_review
                    queue_file = self.config.to_review_file
                    stats['to_review'] += 1
                
                # Create queue entry
                entry = QueueEntry(
                    url=blob.url,
                    container=blob.container,
                    name=blob.name,
                    decision=decision.label,
                    reason=decision.reason,
                    source='auto',
                    decided_at=timestamp,
                    policy_version=decision.policy_version,
                    examples_version=decision.examples_version,
                    confidence=decision.confidence
                )
                
                # Add to queue
                add_to_queue(queue_file, entry)
                
                # Log audit entry
                audit_entry = AuditEntry(
                    timestamp=timestamp,
                    blob_name=blob.name,
                    action=f'triage_{decision.label}',
                    source='auto',
                    reason=decision.reason,
                    metadata=json.dumps({
                        'confidence': decision.confidence,
                        'policy_version': decision.policy_version,
                        'examples_version': decision.examples_version
                    })
                )
                log_audit(self.config.audit_log_file, audit_entry)
            
            return stats
            
        except Exception as e:
            raise Exception(f"Failed to run triage batch: {e}") from e
    
    def show_progress(self) -> dict:
        """Show current progress statistics.
        
        Returns:
            Dictionary with statistics:
            - total_blobs: Total number of blobs
            - labeled: Total labeled blobs
            - unlabeled: Total unlabeled blobs
            - to_keep: Number in keep queue
            - to_delete: Number in delete queue
            - to_review: Number in review queue
            - auto_labeled: Number labeled by LLM
            - human_labeled: Number labeled by humans
        """
        return get_statistics(self.config)
    
    def get_unlabeled_count(self) -> int:
        """Get count of unlabeled blobs.
        
        Returns:
            Number of unlabeled blobs
        """
        stats = get_statistics(self.config)
        return stats.get('unlabeled', 0)
    
    def archive_artifacts(self, archive_dir: str) -> str:
        """Archive all cleanup artifacts to a directory.
        
        Copies all CSV files, logs, and metadata to an archive directory
        with timestamp for record keeping.
        
        Args:
            archive_dir: Base directory for archives
            
        Returns:
            Path to the created archive directory
            
        Raises:
            IOError: If archiving fails
        """
        try:
            import shutil
            
            # Create timestamped archive directory
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            archive_path = Path(archive_dir) / f"cleanup_archive_{timestamp}"
            archive_path.mkdir(parents=True, exist_ok=True)
            
            # List of files to archive
            files_to_archive = [
                self.config.manifest_file,
                self.config.to_keep_file,
                self.config.to_delete_file,
                self.config.to_review_file,
                self.config.audit_log_file,
                self.config.policy_file,
                self.config.few_shot_file,
            ]
            
            # Copy each file if it exists
            archived_count = 0
            for file_path in files_to_archive:
                src = Path(file_path)
                if src.exists():
                    dst = archive_path / src.name
                    shutil.copy2(src, dst)
                    archived_count += 1
            
            # Create archive metadata
            stats = get_statistics(self.config)
            # Convert numpy int64 to regular int for JSON serialization
            stats_serializable = {k: int(v) if isinstance(v, (int, type(pd.NA))) else v 
                                 for k, v in stats.items()}
            
            metadata = {
                'timestamp': timestamp,
                'archived_files': archived_count,
                'statistics': stats_serializable,
                'config': {
                    'container_name': self.config.container_name,
                    'confidence_threshold': self.config.confidence_threshold,
                    'self_consistency_runs': self.config.self_consistency_runs
                }
            }
            
            metadata_path = archive_path / 'archive_metadata.json'
            with metadata_path.open('w') as f:
                json.dump(metadata, f, indent=2, default=int)
            
            # Log audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.utcnow().isoformat(),
                blob_name='archive',
                action='artifacts_archived',
                source='system',
                reason=f'Archived {archived_count} files to {archive_path}',
                metadata=json.dumps(metadata, default=int)
            )
            log_audit(self.config.audit_log_file, audit_entry)
            
            return str(archive_path)
            
        except Exception as e:
            raise IOError(f"Failed to archive artifacts: {e}") from e
    
    def get_next_review_item(self) -> Optional[dict]:
        """Get the next item from the review queue.
        
        Returns:
            Dictionary with blob information or None if queue is empty
        """
        try:
            review_entries = load_queue(self.config.to_review_file)
            
            if not review_entries:
                return None
            
            # Get first entry
            entry = review_entries[0]
            
            # Load manifest to get full blob info
            manifest_path = Path(self.config.manifest_file)
            if not manifest_path.exists():
                # Return basic info from queue
                return {
                    'name': entry.name,
                    'url': entry.url,
                    'decision': entry.decision,
                    'reason': entry.reason,
                    'confidence': entry.confidence,
                    'preview': ''
                }
            
            # Load manifest and find blob
            manifest_df = pd.read_csv(manifest_path)
            blob_row = manifest_df[manifest_df['name'] == entry.name]
            
            if blob_row.empty:
                # Return basic info
                return {
                    'name': entry.name,
                    'url': entry.url,
                    'decision': entry.decision,
                    'reason': entry.reason,
                    'confidence': entry.confidence,
                    'preview': ''
                }
            
            # Return full info
            row = blob_row.iloc[0]
            return {
                'name': entry.name,
                'url': entry.url,
                'path': row.get('path', ''),
                'size': int(row.get('size', 0)),
                'content_type': row.get('content_type', ''),
                'last_modified': row.get('last_modified', ''),
                'preview': row.get('preview', ''),
                'decision': entry.decision,
                'reason': entry.reason,
                'confidence': entry.confidence
            }
            
        except Exception:
            return None
