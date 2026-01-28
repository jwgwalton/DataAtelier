"""
Basic Usage Example - Azure Blob Cleanup TUI

This example demonstrates the simplest way to use the Azure Blob Cleanup tool.
It connects to Azure Storage, inventories blobs, and opens the TUI for review.
"""

import os
from pathlib import Path

# Mock setup for demonstration
def setup_environment():
    """Set up required environment variables."""
    print("Setting up environment variables...")
    
    # In a real scenario, you would set these to actual values
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = (
        "DefaultEndpointsProtocol=https;"
        "AccountName=mystorageaccount;"
        "AccountKey=fake_key_for_demo;"
        "EndpointSuffix=core.windows.net"
    )
    os.environ["AZURE_BLOB_CONTAINER"] = "my-container"
    os.environ["OPENAI_API_KEY"] = "sk-fake-key-for-demo"
    
    print("✓ Environment configured")


def basic_usage():
    """
    Basic usage example showing the main workflow.
    
    Steps:
    1. Set up environment variables
    2. Run the application with minimal options
    3. Use the TUI to review and label blobs
    4. Delete approved items
    """
    print("\n" + "="*60)
    print("BASIC USAGE EXAMPLE")
    print("="*60 + "\n")
    
    # Step 1: Setup
    setup_environment()
    
    # Step 2: Show the command that would be run
    print("\nCommand to run:")
    print("  python azure_blob_cleanup_tui.py run --container my-container")
    
    print("\nWhat happens next:")
    print("  1. Application connects to Azure Storage")
    print("  2. Enumerates blobs in the container")
    print("  3. Generates previews for text files")
    print("  4. Opens TUI for review")
    print("  5. LLM worker (optional) classifies files in background")
    print("  6. You review and label remaining items")
    print("  7. When 100% labeled, you can execute deletion")
    
    print("\nKey TUI shortcuts:")
    print("  K - Mark as Keep")
    print("  D - Mark as Delete")
    print("  H - Mark for Human Review")
    print("  G - Run LLM triage manually")
    print("  X - Execute deletion (when ready)")
    print("  ? - Show help")
    print("  Q - Quit")


if __name__ == "__main__":
    basic_usage()
    
    print("\n" + "="*60)
    print("To run this for real, ensure you have:")
    print("  1. Valid Azure Storage credentials")
    print("  2. Valid OpenAI API key (or use --llm-off)")
    print("  3. Installed dependencies: pip install -r requirements.txt")
    print("="*60 + "\n")
