"""
Example usage of the Azure Blob Cleanup module.

This script demonstrates the complete workflow:
1. Configuration setup
2. Inventory creation
3. LLM-based triage
4. Human review (in notebooks)
5. Deletion execution
"""

from dataatelier.blob_cleanup import (
    BlobCleanupConfig,
    AzureBlobCleanup,
    create_cleanup_tool,
    quick_start,
)


def example_basic_usage():
    """Example 1: Basic usage with environment variables."""
    print("=" * 70)
    print("Example 1: Basic Usage")
    print("=" * 70)
    
    # Load configuration from environment (.env file or environment variables)
    config = BlobCleanupConfig.from_env()
    
    # Validate configuration
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        return
    
    print(f"✓ Configuration loaded")
    print(f"  - Container: {config.container_name}")
    print(f"  - LLM Provider: {config.llm_provider}")
    print(f"  - LLM Model: {config.llm_model}")
    print(f"  - Confidence Threshold: {config.confidence_threshold:.0%}")
    print()
    
    # Create cleanup tool
    cleanup = AzureBlobCleanup(config)
    
    # Run full workflow
    print("Running full workflow...")
    cleanup.run_full_workflow(prefix="temp/")  # Optional: filter by prefix
    
    # Get statistics
    stats = cleanup.get_statistics()
    print("\nResults:")
    print(f"  - To Review: {stats['review']['count']} blobs ({stats['review']['total_size_bytes']:,} bytes)")
    print(f"  - To Delete: {stats['delete']['count']} blobs ({stats['delete']['total_size_bytes']:,} bytes)")
    print(f"  - To Keep: {stats['keep']['count']} blobs ({stats['keep']['total_size_bytes']:,} bytes)")


def example_manual_configuration():
    """Example 2: Manual configuration."""
    print("\n" + "=" * 70)
    print("Example 2: Manual Configuration")
    print("=" * 70)
    
    # Create configuration manually
    config = BlobCleanupConfig(
        connection_string="DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=key123==",
        container_name="my-container",
        llm_provider="openai",
        llm_model="gpt-4",
        llm_api_key="sk-...",
        confidence_threshold=0.95,
        self_consistency_runs=3,
        policy_file="llm_policy.md",
        queue_dir="my_cleanup_queues",
    )
    
    print(f"✓ Configuration created")
    print(f"  - Queue directory: {config.queue_dir}")
    print(f"  - Self-consistency runs: {config.self_consistency_runs}")


def example_azure_openai():
    """Example 3: Using Azure OpenAI."""
    print("\n" + "=" * 70)
    print("Example 3: Azure OpenAI Configuration")
    print("=" * 70)
    
    config = BlobCleanupConfig(
        connection_string="<connection-string>",
        container_name="my-container",
        llm_provider="azure_openai",
        llm_model="gpt-4",
        llm_api_key="<azure-openai-key>",
        llm_endpoint="https://my-resource.openai.azure.com/",
        llm_api_version="2024-02-15-preview",
    )
    
    print(f"✓ Azure OpenAI configuration created")
    print(f"  - Endpoint: {config.llm_endpoint}")
    print(f"  - API Version: {config.llm_api_version}")


def example_ollama():
    """Example 4: Using Ollama (local LLM)."""
    print("\n" + "=" * 70)
    print("Example 4: Ollama (Local LLM) Configuration")
    print("=" * 70)
    
    config = BlobCleanupConfig(
        connection_string="<connection-string>",
        container_name="my-container",
        llm_provider="ollama",
        llm_model="llama2",
        llm_endpoint="http://localhost:11434/v1",
    )
    
    print(f"✓ Ollama configuration created")
    print(f"  - Model: {config.llm_model}")
    print(f"  - Endpoint: {config.llm_endpoint}")


def example_step_by_step():
    """Example 5: Step-by-step workflow control."""
    print("\n" + "=" * 70)
    print("Example 5: Step-by-Step Workflow")
    print("=" * 70)
    
    # Create cleanup tool
    cleanup = create_cleanup_tool()
    
    # Step 1: Create inventory
    print("\nStep 1: Creating inventory...")
    manifest = cleanup.inventory.create_manifest(prefix="logs/")
    print(f"  ✓ Found {len(manifest)} blobs")
    
    # Step 2: LLM triage
    print("\nStep 2: Running LLM triage...")
    decisions = cleanup.llm_engine.batch_triage(manifest[:5])  # Triage first 5
    print(f"  ✓ Triaged {len(decisions)} blobs")
    
    # Step 3: Save to queues
    print("\nStep 3: Saving to queues...")
    cleanup.queue_manager.save_triage_decisions(manifest[:5], decisions)
    print(f"  ✓ Decisions saved to queues")
    
    # Step 4: Review statistics
    stats = cleanup.get_statistics()
    print("\nStep 4: Statistics")
    for queue_type in ['review', 'delete', 'keep']:
        count = stats[queue_type]['count']
        size_mb = stats[queue_type]['total_size_bytes'] / (1024 * 1024)
        print(f"  - {queue_type.title()}: {count} blobs, {size_mb:.2f} MB")


def example_deletion():
    """Example 6: Deletion workflow."""
    print("\n" + "=" * 70)
    print("Example 6: Deletion Workflow")
    print("=" * 70)
    
    cleanup = create_cleanup_tool()
    
    # Dry run first
    print("\nDry run analysis:")
    dry_run_result = cleanup.deletion_manager.dry_run()
    print(f"  - Blobs to delete: {dry_run_result['total_blobs']}")
    print(f"  - Total size: {dry_run_result.get('total_size_mb', 0):.2f} MB")
    
    # Execute deletion (dry run)
    print("\nExecuting deletion (dry run)...")
    result = cleanup.deletion_manager.execute_deletion(dry_run=True)
    print(f"  ✓ Dry run complete")
    print(f"  - Would delete: {result['deleted_count']} blobs")
    print(f"  - Failed: {result['failed_count']} blobs")
    
    # Actual deletion (commented out for safety)
    # print("\nExecuting actual deletion...")
    # result = cleanup.deletion_manager.execute_deletion(dry_run=False)
    # print(f"  ✓ Deletion complete: {result['deleted_count']} blobs deleted")


def example_quick_start():
    """Example 7: Quick start convenience function."""
    print("\n" + "=" * 70)
    print("Example 7: Quick Start")
    print("=" * 70)
    
    print("\nUsing quick_start() for one-line execution:")
    print("  cleanup = quick_start()")
    print("  # This will:")
    print("  #   1. Load config from environment")
    print("  #   2. Create inventory")
    print("  #   3. Run LLM triage")
    print("  #   4. Save to queues")


def example_notebook_review():
    """Example 8: Interactive review in Jupyter notebook."""
    print("\n" + "=" * 70)
    print("Example 8: Interactive Review (Jupyter Notebook)")
    print("=" * 70)
    
    print("\nIn a Jupyter notebook:")
    print("""
from dataatelier import create_cleanup_tool

# Create cleanup tool
cleanup = create_cleanup_tool()

# Run triage to populate review queue
cleanup.run_full_workflow()

# Create interactive review UI
review_ui = cleanup.create_review_ui()
display(review_ui)

# The UI provides:
# - Visual preview of each blob
# - LLM recommendation and reasoning
# - Buttons to Keep, Delete, or Skip
# - Progress tracking
# - Audit logging of all decisions

# After review, execute deletion:
result = cleanup.deletion_manager.execute_deletion(dry_run=False)
print(f"Deleted {result['deleted_count']} blobs")
    """)


def example_few_shot_learning():
    """Example 9: Few-shot learning from human decisions."""
    print("\n" + "=" * 70)
    print("Example 9: Few-Shot Learning")
    print("=" * 70)
    
    cleanup = create_cleanup_tool()
    
    # Simulate adding human decisions for few-shot learning
    print("\nAdding human decisions to improve LLM accuracy:")
    print("  - When humans review blobs, their decisions are automatically")
    print("    added to the LLM's few-shot examples")
    print("  - This helps the LLM learn organization-specific patterns")
    print("  - Example decisions are included in future LLM prompts")
    
    # Manual example (normally done through ReviewUI)
    from dataatelier.blob_cleanup import BlobMetadata
    from datetime import datetime, timezone
    
    example_blob = BlobMetadata(
        name="temp/debug.log",
        size=1024,
        last_modified=datetime.now(timezone.utc),
        content_type="text/plain",
        etag="abc",
        preview="[2024-01-28] Debug log content..."
    )
    
    cleanup.llm_engine.add_few_shot_example(
        blob_meta=example_blob,
        decision="DELETE",
        reasoning="Debug log file older than retention period"
    )
    
    print(f"\n  ✓ Added example to few-shot cache")
    print(f"  - Current examples: {len(cleanup.llm_engine.few_shot_examples)}")


def example_custom_policy():
    """Example 10: Using custom policy file."""
    print("\n" + "=" * 70)
    print("Example 10: Custom Policy File")
    print("=" * 70)
    
    print("\nTo use a custom policy:")
    print("  1. Create your policy markdown file (e.g., 'my_policy.md')")
    print("  2. Follow the format in 'llm_policy.md'")
    print("  3. Specify in configuration:")
    print()
    print("config = BlobCleanupConfig(")
    print("    connection_string='...',")
    print("    container_name='...',")
    print("    policy_file='my_policy.md',  # Custom policy")
    print("    # ... other settings")
    print(")")
    print()
    print("Policy versioning:")
    print("  - Each policy has an MD5 hash")
    print("  - Hash is stored with each decision")
    print("  - This enables audit trail of which policy version was used")


if __name__ == "__main__":
    """Run examples (with mock data - not actual Azure operations)."""
    
    print("\n" + "=" * 70)
    print("Azure Blob Cleanup Module - Usage Examples")
    print("=" * 70)
    print()
    print("NOTE: These are demonstration examples.")
    print("To run actual cleanup, configure environment variables in .env file:")
    print("  - AZURE_STORAGE_CONNECTION_STRING")
    print("  - AZURE_CONTAINER_NAME")
    print("  - LLM_API_KEY (or OPENAI_API_KEY)")
    print("  - LLM_PROVIDER (openai, azure_openai, or ollama)")
    print("  - LLM_MODEL")
    print()
    
    # Run examples that don't require actual Azure credentials
    example_manual_configuration()
    example_azure_openai()
    example_ollama()
    example_step_by_step.__doc__ and print(example_step_by_step.__doc__)
    example_deletion.__doc__ and print(example_deletion.__doc__)
    example_quick_start()
    example_notebook_review()
    example_few_shot_learning()
    example_custom_policy()
    
    print("\n" + "=" * 70)
    print("Examples complete!")
    print("=" * 70)
    print("\nFor actual usage, see README.md or azure_blob_cleanup.ipynb")
    print()
