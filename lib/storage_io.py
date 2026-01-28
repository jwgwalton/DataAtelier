"""Azure Blob Storage I/O operations."""

import io
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import chardet
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContainerClient

logger = logging.getLogger(__name__)


class StorageIO:
    """Azure Blob Storage helper for listing, previewing, and deleting blobs."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        account_url: Optional[str] = None,
        sas_token: Optional[str] = None,
    ):
        """Initialize storage client.
        
        Args:
            connection_string: Azure Storage connection string
            account_url: Azure Storage account URL
            sas_token: SAS token for authentication
        """
        if connection_string:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
        elif account_url and sas_token:
            self.blob_service_client = BlobServiceClient(
                account_url=account_url, credential=sas_token
            )
        elif account_url:
            # Try default credentials
            from azure.identity import DefaultAzureCredential
            self.blob_service_client = BlobServiceClient(
                account_url=account_url, credential=DefaultAzureCredential()
            )
        else:
            raise ValueError(
                "Must provide either connection_string or account_url (with optional sas_token)"
            )

    def get_container_client(self, container_name: str) -> ContainerClient:
        """Get a container client."""
        return self.blob_service_client.get_container_client(container_name)

    def list_blobs(
        self,
        container_name: str,
        prefix: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[Dict]:
        """List blobs in a container with optional prefix filter.
        
        Args:
            container_name: Container to list from
            prefix: Optional path prefix filter
            max_results: Maximum number of results to return
            
        Returns:
            List of blob metadata dictionaries
        """
        container_client = self.get_container_client(container_name)
        blobs = []
        
        try:
            blob_list = container_client.list_blobs(name_starts_with=prefix)
            
            for idx, blob in enumerate(blob_list):
                if max_results and idx >= max_results:
                    break
                    
                blob_dict = {
                    "container": container_name,
                    "name": blob.name,
                    "url": f"{container_client.url}/{blob.name}",
                    "size": blob.size,
                    "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                    "content_type": blob.content_type,
                }
                blobs.append(blob_dict)
                
        except Exception as e:
            logger.error(f"Error listing blobs: {e}")
            raise
            
        return blobs

    def get_blob_preview(
        self,
        container_name: str,
        blob_name: str,
        max_bytes: int = 4096,
    ) -> Tuple[str, bool]:
        """Download and decode a preview of a blob's content.
        
        Args:
            container_name: Container name
            blob_name: Blob name/path
            max_bytes: Maximum bytes to download
            
        Returns:
            Tuple of (preview_text, is_text)
        """
        container_client = self.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        
        try:
            # Download first max_bytes
            stream = blob_client.download_blob(max_concurrency=1, length=max_bytes)
            data = stream.readall()
            
            # Try to decode as text
            text, is_text = self._decode_bytes(data)
            return text, is_text
            
        except ResourceNotFoundError:
            logger.warning(f"Blob not found: {blob_name}")
            return "", False
        except Exception as e:
            logger.error(f"Error downloading blob preview for {blob_name}: {e}")
            return f"[Error: {str(e)}]", False

    def _decode_bytes(self, data: bytes) -> Tuple[str, bool]:
        """Attempt to decode bytes as text.
        
        Args:
            data: Bytes to decode
            
        Returns:
            Tuple of (decoded_text, is_text)
        """
        if not data:
            return "", False
            
        # Try UTF-8 first
        try:
            text = data.decode("utf-8")
            return text, True
        except UnicodeDecodeError:
            pass
            
        # Try chardet detection
        try:
            result = chardet.detect(data)
            if result["encoding"] and result["confidence"] > 0.7:
                text = data.decode(result["encoding"], errors="replace")
                return text, True
        except Exception:
            pass
            
        # Not text
        return "[Binary content]", False

    def is_text_content(self, content_type: Optional[str], blob_name: str) -> bool:
        """Determine if a blob is likely to contain text.
        
        Args:
            content_type: MIME type
            blob_name: Blob name/path for extension check
            
        Returns:
            True if likely text content
        """
        # Check content type
        if content_type:
            if content_type.startswith("text/"):
                return True
            if content_type in [
                "application/json",
                "application/xml",
                "application/javascript",
                "application/x-yaml",
            ]:
                return True
                
        # Check extension
        text_extensions = {
            ".txt", ".csv", ".json", ".xml", ".md", ".log",
            ".ini", ".yaml", ".yml", ".conf", ".config",
            ".js", ".py", ".java", ".c", ".cpp", ".h",
            ".html", ".htm", ".css", ".sql", ".sh",
        }
        
        for ext in text_extensions:
            if blob_name.lower().endswith(ext):
                return True
                
        return False

    def delete_blob(
        self,
        container_name: str,
        blob_name: str,
        delete_snapshots: str = "include",
    ) -> bool:
        """Delete a blob.
        
        Args:
            container_name: Container name
            blob_name: Blob name/path
            delete_snapshots: How to handle snapshots ("include" or "only")
            
        Returns:
            True if deleted successfully
        """
        container_client = self.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        
        try:
            blob_client.delete_blob(delete_snapshots=delete_snapshots)
            logger.info(f"Deleted blob: {blob_name}")
            return True
        except ResourceNotFoundError:
            logger.warning(f"Blob not found for deletion: {blob_name}")
            return False
        except Exception as e:
            logger.error(f"Error deleting blob {blob_name}: {e}")
            return False

    def batch_delete_blobs(
        self,
        container_name: str,
        blob_names: List[str],
        delete_snapshots: str = "include",
    ) -> Dict[str, bool]:
        """Delete multiple blobs.
        
        Args:
            container_name: Container name
            blob_names: List of blob names
            delete_snapshots: How to handle snapshots
            
        Returns:
            Dict mapping blob_name to success status
        """
        results = {}
        for blob_name in blob_names:
            results[blob_name] = self.delete_blob(
                container_name, blob_name, delete_snapshots
            )
        return results
