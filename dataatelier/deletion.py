"""Deletion operations for DataAtelier."""

from datetime import datetime
from pathlib import Path
import json
from typing import Optional

from .models import AuditEntry
from .queue import load_queue, get_statistics
from .audit import log_audit


def dry_run_report(config) -> dict:
    """Generate a dry run report of what would be deleted.
    
    Args:
        config: Configuration object with queue file paths
        
    Returns:
        Dictionary with statistics about planned deletions:
        - total_to_delete: Number of blobs marked for deletion
        - total_size_bytes: Total size of blobs to delete
        - by_source: Breakdown by source (auto vs human)
        - sample_blobs: Sample of blobs to be deleted (up to 10)
    """
    try:
        # Load the to_delete queue
        to_delete_entries = load_queue(config.to_delete_file)
        
        total_size = 0
        by_source = {'auto': 0, 'human': 0}
        sample_blobs = []
        
        for i, entry in enumerate(to_delete_entries):
            # Count by source
            if entry.source in by_source:
                by_source[entry.source] += 1
            
            # Add to sample (first 10)
            if i < 10:
                sample_blobs.append({
                    'name': entry.name,
                    'reason': entry.reason,
                    'source': entry.source,
                    'confidence': entry.confidence
                })
        
        return {
            'total_to_delete': len(to_delete_entries),
            'total_size_bytes': total_size,  # Note: size not stored in queue, would need manifest lookup
            'by_source': by_source,
            'sample_blobs': sample_blobs
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'total_to_delete': 0,
            'total_size_bytes': 0,
            'by_source': {},
            'sample_blobs': []
        }


def check_coverage(config) -> tuple[bool, int]:
    """Check if all blobs have been labeled (100% coverage).
    
    Args:
        config: Configuration object with file paths
        
    Returns:
        Tuple of (is_complete, unlabeled_count)
        - is_complete: True if all blobs are labeled
        - unlabeled_count: Number of unlabeled blobs
    """
    try:
        stats = get_statistics(config)
        unlabeled_count = stats.get('unlabeled', 0)
        is_complete = unlabeled_count == 0
        
        return is_complete, unlabeled_count
        
    except Exception:
        # If we can't determine coverage, be conservative
        return False, -1


def execute_deletion(
    config,
    dry_run: bool = True,
    storage_client: Optional[object] = None
) -> dict:
    """Execute deletion of blobs marked for deletion.
    
    Args:
        config: Configuration object with settings
        dry_run: If True, don't actually delete (default True)
        storage_client: Optional Azure storage container client
        
    Returns:
        Dictionary with execution results:
        - dry_run: Whether this was a dry run
        - deleted_count: Number of blobs deleted
        - failed_count: Number of deletion failures
        - errors: List of error messages
        - coverage_check_passed: Whether 100% coverage check passed
    """
    result = {
        'dry_run': dry_run,
        'deleted_count': 0,
        'failed_count': 0,
        'errors': [],
        'coverage_check_passed': False
    }
    
    # Check coverage first
    is_complete, unlabeled_count = check_coverage(config)
    result['coverage_check_passed'] = is_complete
    
    if not is_complete:
        result['errors'].append(
            f'Coverage check failed: {unlabeled_count} blobs are unlabeled. '
            'All blobs must be labeled before deletion.'
        )
        return result
    
    # Load to_delete queue
    try:
        to_delete_entries = load_queue(config.to_delete_file)
    except Exception as e:
        result['errors'].append(f'Failed to load to_delete queue: {e}')
        return result
    
    if not to_delete_entries:
        return result
    
    # Extract blob names
    blob_names = [entry.name for entry in to_delete_entries]
    
    # Delete blobs
    deletion_results = delete_blobs_batch(
        config=config,
        blob_names=blob_names,
        dry_run=dry_run,
        storage_client=storage_client
    )
    
    # Count results
    for res in deletion_results:
        if res.get('success'):
            result['deleted_count'] += 1
        else:
            result['failed_count'] += 1
            if 'error' in res:
                result['errors'].append(f"{res['blob_name']}: {res['error']}")
    
    return result


def delete_blobs_batch(
    config,
    blob_names: list[str],
    dry_run: bool = True,
    storage_client: Optional[object] = None
) -> list[dict]:
    """Delete a batch of blobs from Azure Storage.
    
    Args:
        config: Configuration object with settings
        blob_names: List of blob names to delete
        dry_run: If True, don't actually delete (default True)
        storage_client: Optional Azure storage container client
        
    Returns:
        List of dictionaries with results per blob:
        - blob_name: Name of the blob
        - success: Whether deletion succeeded
        - error: Error message if failed
        - timestamp: Timestamp of deletion attempt
    """
    results = []
    timestamp = datetime.utcnow().isoformat()
    
    for blob_name in blob_names:
        result = {
            'blob_name': blob_name,
            'success': False,
            'timestamp': timestamp
        }
        
        if dry_run:
            # In dry run mode, just record what would happen
            result['success'] = True
            result['dry_run'] = True
            
            # Log to audit
            try:
                audit_entry = AuditEntry(
                    timestamp=timestamp,
                    blob_name=blob_name,
                    action='delete_dry_run',
                    source='system',
                    reason='Dry run deletion',
                    metadata=json.dumps({'dry_run': True})
                )
                log_audit(config.audit_log_file, audit_entry)
            except Exception:
                pass  # Don't fail dry run if audit logging fails
            
        else:
            # Actually delete the blob
            if storage_client is None:
                result['error'] = 'No storage client provided'
                results.append(result)
                continue
            
            try:
                # Get blob client and delete
                blob_client = storage_client.get_blob_client(blob_name)
                blob_client.delete_blob()
                
                result['success'] = True
                
                # Log to audit
                try:
                    audit_entry = AuditEntry(
                        timestamp=timestamp,
                        blob_name=blob_name,
                        action='delete',
                        source='system',
                        reason='Automated deletion',
                        metadata=json.dumps({'success': True})
                    )
                    log_audit(config.audit_log_file, audit_entry)
                except Exception:
                    pass  # Don't fail deletion if audit logging fails
                
            except Exception as e:
                result['error'] = str(e)
                
                # Log failure to audit
                try:
                    audit_entry = AuditEntry(
                        timestamp=timestamp,
                        blob_name=blob_name,
                        action='delete_failed',
                        source='system',
                        reason=f'Deletion failed: {str(e)}',
                        metadata=json.dumps({'error': str(e)})
                    )
                    log_audit(config.audit_log_file, audit_entry)
                except Exception:
                    pass
        
        results.append(result)
    
    return results
