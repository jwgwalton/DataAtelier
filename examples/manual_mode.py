"""
Manual Mode Example - No LLM Required

This example shows how to use the tool in manual mode without LLM assistance.
Perfect for when you don't have an OpenAI API key or prefer full manual control.
"""

import os


def setup_manual_mode():
    """Set up for manual mode (no LLM)."""
    print("Setting up manual mode configuration...")
    
    # Only Azure Storage credentials needed
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = (
        "DefaultEndpointsProtocol=https;"
        "AccountName=mystorageaccount;"
        "AccountKey=fake_key_for_demo;"
        "EndpointSuffix=core.windows.net"
    )
    os.environ["AZURE_BLOB_CONTAINER"] = "logs-archive"
    
    print("✓ Manual mode configured (no LLM required)")


def manual_workflow():
    """
    Manual workflow without LLM assistance.
    
    This mode is useful when:
    - You don't have an OpenAI API key
    - You prefer full manual control
    - You have a small number of files
    - The classification logic is complex and human-specific
    """
    print("\n" + "="*60)
    print("MANUAL MODE EXAMPLE")
    print("="*60 + "\n")
    
    setup_manual_mode()
    
    print("\nCommand to run:")
    print("  python azure_blob_cleanup_tui.py run \\")
    print("    --container logs-archive \\")
    print("    --llm-off \\")
    print("    --prefix '2023/'")
    
    print("\nWorkflow:")
    print("  1. Application inventories blobs (no LLM calls)")
    print("  2. TUI opens with all items in 'review' queue")
    print("  3. You manually review each item:")
    print("     - Press K to keep")
    print("     - Press D to delete")
    print("     - Use Enter to view details")
    print("  4. When 100% labeled, execute deletion with X")
    
    print("\nBenefits of manual mode:")
    print("  ✓ No API costs")
    print("  ✓ No API key required")
    print("  ✓ Full human control")
    print("  ✓ Faster for small datasets")
    
    print("\nTips:")
    print("  • Use / to search/filter by filename")
    print("  • Sort by size, date, or name")
    print("  • Use batch mode (B key) for similar files")
    print("  • All decisions logged in audit_log.csv")


def limited_scope_manual():
    """Example: Manual review of specific files."""
    print("\n" + "-"*60)
    print("FOCUSED MANUAL CLEANUP")
    print("-"*60 + "\n")
    
    print("Example: Clean up old log files from 2023")
    print("\nCommand:")
    print("  python azure_blob_cleanup_tui.py run \\")
    print("    --container logs \\")
    print("    --prefix 'app-logs/2023/' \\")
    print("    --max-files 100 \\")
    print("    --llm-off")
    
    print("\nThis limits the scope to:")
    print("  • Container: 'logs'")
    print("  • Path prefix: 'app-logs/2023/'")
    print("  • Maximum: 100 files")
    print("  • Mode: Manual (no LLM)")


if __name__ == "__main__":
    manual_workflow()
    limited_scope_manual()
    
    print("\n" + "="*60)
    print("Manual mode is perfect for small, focused cleanup tasks!")
    print("="*60 + "\n")
