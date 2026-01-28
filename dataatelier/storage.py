"""Azure Blob Storage operations for DataAtelier."""

from typing import Optional
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.core.exceptions import AzureError, ResourceNotFoundError

from .models import BlobMetadata
from .config import Config


def get_container_client(config: Config) -> ContainerClient:
    """Get Azure Blob Storage container client.
    
    Args:
        config: Configuration object with storage settings
        
    Returns:
        ContainerClient instance
        
    Raises:
        ValueError: If connection string or container name is missing
        AzureError: If connection to Azure fails
    """
    if not config.storage_connection_string:
        raise ValueError("Storage connection string is required")
    if not config.container_name:
        raise ValueError("Container name is required")
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            config.storage_connection_string
        )
        container_client = blob_service_client.get_container_client(config.container_name)
        return container_client
    except Exception as e:
        raise AzureError(f"Failed to connect to Azure Storage: {e}") from e


def list_blobs(config: Config, name_prefix: Optional[str] = None) -> list[BlobMetadata]:
    """List all blobs in the configured container.
    
    Args:
        config: Configuration object with storage settings
        name_prefix: Optional prefix to filter blob names
        
    Returns:
        List of BlobMetadata objects
        
    Raises:
        AzureError: If listing blobs fails
    """
    container_client = get_container_client(config)
    blobs = []
    
    try:
        blob_list = container_client.list_blobs(name_starts_with=name_prefix)
        
        for blob in blob_list:
            blob_metadata = BlobMetadata(
                url=f"{container_client.url}/{blob.name}",
                container=config.container_name,
                name=blob.name,
                path=blob.name,
                size=blob.size or 0,
                last_modified=blob.last_modified,
                content_type=blob.content_settings.content_type or "application/octet-stream",
                etag=blob.etag or "",
            )
            blobs.append(blob_metadata)
            
        return blobs
        
    except Exception as e:
        raise AzureError(f"Failed to list blobs: {e}") from e


def download_blob_content(
    config: Config, 
    blob_name: str, 
    max_bytes: Optional[int] = None
) -> bytes:
    """Download blob content from Azure Storage.
    
    Args:
        config: Configuration object with storage settings
        blob_name: Name of the blob to download
        max_bytes: Maximum number of bytes to download (None for full download)
        
    Returns:
        Blob content as bytes
        
    Raises:
        ResourceNotFoundError: If blob doesn't exist
        AzureError: If download fails
    """
    container_client = get_container_client(config)
    
    try:
        blob_client = container_client.get_blob_client(blob_name)
        
        if max_bytes is not None:
            # Download only the specified number of bytes
            downloader = blob_client.download_blob(max_concurrency=1, length=max_bytes)
        else:
            # Download the entire blob
            downloader = blob_client.download_blob()
            
        content = downloader.readall()
        return content
        
    except ResourceNotFoundError:
        raise ResourceNotFoundError(f"Blob not found: {blob_name}")
    except Exception as e:
        raise AzureError(f"Failed to download blob '{blob_name}': {e}") from e


def delete_blob(config: Config, blob_name: str) -> bool:
    """Delete a blob from Azure Storage.
    
    Args:
        config: Configuration object with storage settings
        blob_name: Name of the blob to delete
        
    Returns:
        True if deletion was successful, False otherwise
        
    Raises:
        AzureError: If deletion fails for reasons other than blob not found
    """
    container_client = get_container_client(config)
    
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.delete_blob()
        return True
        
    except ResourceNotFoundError:
        # Blob doesn't exist, consider this a successful deletion
        return False
    except Exception as e:
        raise AzureError(f"Failed to delete blob '{blob_name}': {e}") from e
