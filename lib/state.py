"""State management for CSV/JSON/Parquet files."""

import csv
import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class StateManager:
    """Manages state files (CSV, JSON, Parquet) with thread-safe operations."""

    def __init__(self, work_dir: str = "."):
        """Initialize state manager.
        
        Args:
            work_dir: Working directory for state files
        """
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.manifest_path = self.work_dir / "manifest.csv"
        self.to_review_path = self.work_dir / "to_review.csv"
        self.to_delete_path = self.work_dir / "to_delete.csv"
        self.to_keep_path = self.work_dir / "to_keep.csv"
        self.audit_log_path = self.work_dir / "audit_log.csv"
        self.examples_path = self.work_dir / "few_shot_examples.jsonl"
        self.predictions_path = self.work_dir / "llm_predictions.parquet"
        self.policy_path = self.work_dir / "llm_policy.md"
        
        # Thread lock for file operations
        self._lock = threading.Lock()
        
        # Version tracking
        self._policy_version: Optional[str] = None
        self._examples_version: Optional[str] = None

    # Manifest operations
    
    def write_manifest(self, blobs: List[Dict]) -> None:
        """Write or update manifest.csv with blob metadata.
        
        Args:
            blobs: List of blob dictionaries
        """
        with self._lock:
            # Read existing manifest if it exists
            existing = {}
            if self.manifest_path.exists():
                try:
                    df = pd.read_csv(self.manifest_path)
                    for _, row in df.iterrows():
                        existing[row["url"]] = row.to_dict()
                except Exception as e:
                    logger.warning(f"Error reading existing manifest: {e}")
            
            # Merge with new blobs (no duplicates)
            for blob in blobs:
                existing[blob["url"]] = blob
            
            # Write updated manifest
            df = pd.DataFrame(list(existing.values()))
            if not df.empty:
                columns = ["container", "name", "url", "size", "last_modified", 
                          "content_type", "preview_text"]
                # Ensure all columns exist
                for col in columns:
                    if col not in df.columns:
                        df[col] = ""
                df = df[columns]
            df.to_csv(self.manifest_path, index=False)
            logger.info(f"Wrote {len(df)} entries to manifest")

    def read_manifest(self) -> pd.DataFrame:
        """Read manifest.csv.
        
        Returns:
            DataFrame with manifest data
        """
        if not self.manifest_path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(self.manifest_path)
        except Exception as e:
            logger.error(f"Error reading manifest: {e}")
            return pd.DataFrame()

    # Queue operations
    
    def _read_queue(self, path: Path) -> pd.DataFrame:
        """Read a queue CSV file."""
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception as e:
            logger.error(f"Error reading queue {path}: {e}")
            return pd.DataFrame()

    def _write_queue(self, path: Path, df: pd.DataFrame) -> None:
        """Write a queue CSV file."""
        columns = ["url", "container", "name", "decision", "reason", "source",
                  "decided_at", "policy_version", "examples_version"]
        # Ensure all columns exist
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
        df.to_csv(path, index=False)

    def read_queue(self, queue_name: str) -> pd.DataFrame:
        """Read a queue by name.
        
        Args:
            queue_name: "review", "delete", or "keep"
            
        Returns:
            DataFrame with queue data
        """
        path_map = {
            "review": self.to_review_path,
            "delete": self.to_delete_path,
            "keep": self.to_keep_path,
        }
        if queue_name not in path_map:
            raise ValueError(f"Invalid queue name: {queue_name}")
        return self._read_queue(path_map[queue_name])

    def add_to_queue(
        self,
        queue_name: str,
        items: List[Dict],
        source: str = "auto",
    ) -> None:
        """Add items to a queue, removing duplicates.
        
        Args:
            queue_name: "review", "delete", or "keep"
            items: List of item dictionaries with url, container, name, reason, etc.
            source: "auto" or "human"
        """
        with self._lock:
            path_map = {
                "review": self.to_review_path,
                "delete": self.to_delete_path,
                "keep": self.to_keep_path,
            }
            if queue_name not in path_map:
                raise ValueError(f"Invalid queue name: {queue_name}")
            
            path = path_map[queue_name]
            df = self._read_queue(path)
            
            # Add new items
            for item in items:
                item_copy = item.copy()
                item_copy["decision"] = queue_name
                item_copy["source"] = source
                item_copy["decided_at"] = datetime.utcnow().isoformat()
                item_copy["policy_version"] = item_copy.get("policy_version", 
                                                            self.get_policy_version())
                item_copy["examples_version"] = item_copy.get("examples_version",
                                                               self.get_examples_version())
                
                # Check if already exists
                if not df.empty and item_copy["url"] in df["url"].values:
                    # Update existing - replace the entire row
                    idx = df.index[df["url"] == item_copy["url"]].tolist()[0]
                    for key, value in item_copy.items():
                        df.at[idx, key] = value
                else:
                    # Append new
                    df = pd.concat([df, pd.DataFrame([item_copy])], ignore_index=True)
            
            self._write_queue(path, df)
            logger.info(f"Added {len(items)} items to {queue_name} queue")

    def move_between_queues(
        self,
        url: str,
        from_queue: str,
        to_queue: str,
        reason: str = "",
        source: str = "human",
    ) -> bool:
        """Move an item from one queue to another.
        
        Args:
            url: Blob URL
            from_queue: Source queue name
            to_queue: Destination queue name
            reason: Reason for the move
            source: "auto" or "human"
            
        Returns:
            True if moved successfully
        """
        with self._lock:
            # Read from queue
            from_df = self.read_queue(from_queue)
            if from_df.empty or url not in from_df["url"].values:
                logger.warning(f"URL {url} not found in {from_queue} queue")
                return False
            
            # Get item
            item = from_df[from_df["url"] == url].iloc[0].to_dict()
            
            # Remove from source queue
            from_df = from_df[from_df["url"] != url]
            path_map = {
                "review": self.to_review_path,
                "delete": self.to_delete_path,
                "keep": self.to_keep_path,
            }
            self._write_queue(path_map[from_queue], from_df)
            
            # Add to destination queue
            item["decision"] = to_queue
            item["reason"] = reason or item.get("reason", "")
            item["source"] = source
            self.add_to_queue(to_queue, [item], source)
            
            # Log to audit
            self.append_audit_log({
                "url": url,
                "container": item.get("container", ""),
                "name": item.get("name", ""),
                "action": f"{source}_{to_queue}",
                "reason": reason,
                "actor": source,
                "at": datetime.utcnow().isoformat(),
                "policy_version": self.get_policy_version(),
                "examples_version": self.get_examples_version(),
            })
            
            return True

    def remove_from_all_queues(self, url: str) -> None:
        """Remove an item from all queues.
        
        Args:
            url: Blob URL
        """
        with self._lock:
            for queue_name in ["review", "delete", "keep"]:
                df = self.read_queue(queue_name)
                if not df.empty and url in df["url"].values:
                    df = df[df["url"] != url]
                    path_map = {
                        "review": self.to_review_path,
                        "delete": self.to_delete_path,
                        "keep": self.to_keep_path,
                    }
                    self._write_queue(path_map[queue_name], df)

    # Audit log
    
    def append_audit_log(self, entry: Dict) -> None:
        """Append entry to audit log.
        
        Args:
            entry: Dictionary with audit log fields
        """
        with self._lock:
            # Read existing
            if self.audit_log_path.exists():
                df = pd.read_csv(self.audit_log_path)
            else:
                df = pd.DataFrame()
            
            # Append
            df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
            
            # Write
            columns = ["url", "container", "name", "action", "reason", "actor",
                      "at", "policy_version", "examples_version"]
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            df = df[columns]
            df.to_csv(self.audit_log_path, index=False)

    # Policy and examples versioning
    
    def get_policy_version(self) -> str:
        """Get current policy version (hash of policy file).
        
        Returns:
            Hash string or "none" if no policy
        """
        if not self.policy_path.exists():
            return "none"
        
        try:
            content = self.policy_path.read_text()
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception as e:
            logger.error(f"Error reading policy: {e}")
            return "error"

    def get_examples_version(self) -> str:
        """Get current examples version (hash of examples file).
        
        Returns:
            Hash string or "none" if no examples
        """
        if not self.examples_path.exists():
            return "none"
        
        try:
            content = self.examples_path.read_text()
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception as e:
            logger.error(f"Error reading examples: {e}")
            return "error"

    # LLM predictions cache
    
    def read_predictions(self) -> pd.DataFrame:
        """Read LLM predictions from Parquet.
        
        Returns:
            DataFrame with predictions
        """
        if not self.predictions_path.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(self.predictions_path)
        except Exception as e:
            logger.error(f"Error reading predictions: {e}")
            return pd.DataFrame()

    def write_predictions(self, predictions: List[Dict]) -> None:
        """Write LLM predictions to Parquet.
        
        Args:
            predictions: List of prediction dictionaries
        """
        with self._lock:
            # Read existing
            existing = self.read_predictions()
            
            # Append new
            new_df = pd.DataFrame(predictions)
            if not existing.empty:
                df = pd.concat([existing, new_df], ignore_index=True)
            else:
                df = new_df
            
            # Write
            if not df.empty:
                df.to_parquet(self.predictions_path, index=False)

    # Statistics
    
    def get_coverage_stats(self) -> Dict[str, Any]:
        """Get coverage statistics.
        
        Returns:
            Dictionary with stats
        """
        manifest = self.read_manifest()
        total = len(manifest)
        
        review_df = self.read_queue("review")
        delete_df = self.read_queue("delete")
        keep_df = self.read_queue("keep")
        
        labeled = len(delete_df) + len(keep_df)
        
        return {
            "total": total,
            "labeled": labeled,
            "remaining": total - labeled,
            "to_review": len(review_df),
            "to_delete": len(delete_df),
            "to_keep": len(keep_df),
            "coverage": labeled / total if total > 0 else 0,
        }

    def get_unlabeled_urls(self) -> Set[str]:
        """Get URLs that are not in any queue.
        
        Returns:
            Set of URLs
        """
        manifest = self.read_manifest()
        if manifest.empty:
            return set()
        
        all_urls = set(manifest["url"].values)
        
        review_df = self.read_queue("review")
        delete_df = self.read_queue("delete")
        keep_df = self.read_queue("keep")
        
        labeled_urls = set()
        for df in [review_df, delete_df, keep_df]:
            if not df.empty:
                labeled_urls.update(df["url"].values)
        
        return all_urls - labeled_urls

    # Archive
    
    def archive_artifacts(self) -> str:
        """Archive all artifacts to a timestamped directory.
        
        Returns:
            Path to archive directory
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_dir = self.work_dir / "archive" / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        files_to_archive = [
            self.manifest_path,
            self.to_review_path,
            self.to_delete_path,
            self.to_keep_path,
            self.audit_log_path,
            self.examples_path,
            self.predictions_path,
            self.policy_path,
        ]
        
        for file_path in files_to_archive:
            if file_path.exists():
                import shutil
                shutil.copy2(file_path, archive_dir / file_path.name)
        
        logger.info(f"Archived artifacts to {archive_dir}")
        return str(archive_dir)
