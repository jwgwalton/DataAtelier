"""
Custom Policy Example - Tailoring LLM Classification

This example shows how to customize the policy file to guide LLM classification
for your specific use case.
"""

import os
from pathlib import Path


CUSTOM_POLICY = """# Custom Cleanup Policy for Production Logs

## Purpose and Scope
This policy is designed for cleaning up production application logs while
preserving important data for compliance and debugging.

## Positive Signals for DELETE
Files that should be deleted include:
- Access logs older than 90 days (*.access.log)
- Debug logs older than 30 days (*.debug.log)
- Temp files and crash dumps (*.tmp, *.dmp)
- Application cache files (cache/*.*)
- Rotated log files with numeric suffixes (app.log.1, app.log.2, etc.)
- Test data in non-production paths (/test/, /staging/)

## Positive Signals for KEEP
Files that should be kept include:
- Error logs from the last 90 days
- Audit logs (all - required for compliance)
- Security logs (all - required for compliance)
- Configuration files (*.config, *.yaml)
- Current active log files (no numeric suffix)
- Any file in /production/ or /prod/ paths
- Files with 'important', 'audit', or 'security' in the name

## Never-Delete Clauses (Guardrails)
**NEVER** delete files that:
1. Are in /production/, /prod/, or /live/ paths
2. Contain 'audit', 'security', or 'compliance' in the path or name
3. Are configuration files (*.config, *.yaml, *.json in /config/)
4. Are less than 30 days old (unless clearly temporary)
5. Have 'backup' in the path
6. Are in paths containing 'important' or 'critical'

## Edge Cases and Guidance
- Log files exactly 90 days old: Review manually
- Large files (> 1GB): Review to ensure not needed for investigation
- Files with unusual extensions: Review
- Compressed logs (*.gz, *.zip): Keep if within retention period
- Files with 'prod' or 'production' in name but not in path: Review

## Date-Based Retention
- Access logs: 90 days
- Debug logs: 30 days
- Error logs: 90 days
- Audit logs: Keep all
- Security logs: Keep all

## Examples
- `app.log.2023.01.15.gz` (150 days old) → DELETE (rotated, old)
- `audit.log` → KEEP (audit log)
- `prod-api.error.log` → KEEP (production error log)
- `test-debug.log` → DELETE (test data)
- `cache/session-abc123.tmp` → DELETE (cache file)
"""


def create_custom_policy():
    """Create a custom policy file for the cleanup task."""
    print("\n" + "="*60)
    print("CUSTOM POLICY EXAMPLE")
    print("="*60 + "\n")
    
    # Create a work directory for this example
    work_dir = Path("./example-cleanup-session")
    work_dir.mkdir(exist_ok=True)
    
    # Write custom policy
    policy_path = work_dir / "llm_policy.md"
    policy_path.write_text(CUSTOM_POLICY)
    
    print(f"✓ Created custom policy at: {policy_path}")
    print("\nPolicy highlights:")
    print("  • Retention: 90 days for access logs, 30 for debug")
    print("  • Never delete: audit, security, compliance logs")
    print("  • Never delete: production paths")
    print("  • Edge cases: Large files, unusual extensions → review")
    
    return work_dir


def run_with_custom_policy():
    """Example workflow with custom policy."""
    work_dir = create_custom_policy()
    
    print("\nCommand to run:")
    print(f"  python azure_blob_cleanup_tui.py run \\")
    print(f"    --container production-logs \\")
    print(f"    --work-dir {work_dir} \\")
    print(f"    --llm-model gpt-4")
    
    print("\nWorkflow:")
    print("  1. Application loads your custom policy")
    print("  2. LLM uses the policy to classify files")
    print("  3. Files matching never-delete clauses → kept or reviewed")
    print("  4. Clear delete candidates → auto-deleted (if confidence high)")
    print("  5. Borderline cases → queued for human review")
    
    print("\nYou can edit the policy at any time:")
    print("  • Press E in the TUI to open policy in editor")
    print("  • Make changes and save")
    print("  • LLM will use updated policy for new classifications")


def policy_tips():
    """Tips for writing effective policies."""
    print("\n" + "-"*60)
    print("POLICY WRITING TIPS")
    print("-"*60 + "\n")
    
    print("1. BE SPECIFIC:")
    print("   ✓ 'Delete *.tmp files older than 7 days'")
    print("   ✗ 'Delete old files'")
    
    print("\n2. USE CLEAR EXAMPLES:")
    print("   Include actual filenames and expected classification")
    
    print("\n3. DEFINE RETENTION PERIODS:")
    print("   Specify days, not vague terms like 'old' or 'recent'")
    
    print("\n4. NEVER-DELETE CLAUSES:")
    print("   Be explicit about what must never be deleted")
    
    print("\n5. EDGE CASES:")
    print("   Document borderline scenarios and how to handle them")
    
    print("\n6. TEST AND ITERATE:")
    print("   • Start with a small batch")
    print("   • Review LLM classifications")
    print("   • Update policy based on mistakes")
    print("   • Add examples for edge cases")


def few_shot_examples():
    """How to add few-shot examples."""
    print("\n" + "-"*60)
    print("FEW-SHOT EXAMPLES")
    print("-"*60 + "\n")
    
    print("Improve LLM accuracy by adding examples in the TUI:")
    print("\n1. Navigate to a correctly labeled item")
    print("2. Press A to add as example")
    print("3. Enter reason: 'Old rotated log, safe to delete'")
    print("4. Enter cues: 'rotated, old, .log'")
    print("5. Example saved to few_shot_examples.jsonl")
    
    print("\nThe LLM will use these examples to:")
    print("  • Learn from your decisions")
    print("  • Better understand edge cases")
    print("  • Improve classification accuracy")
    
    print("\nExample format (few_shot_examples.jsonl):")
    print("""{
  "label": "delete",
  "reason": "Old rotated log file beyond retention",
  "excerpt": "2023-01-15 INFO Application started...",
  "cues": ["rotated", "old", "numeric suffix"],
  "path_hint": "logs/app.log.2023.01.15.gz",
  "content_type": "application/gzip",
  "decided_at": "2026-01-28T10:30:00Z",
  "reviewer": "admin"
}""")


if __name__ == "__main__":
    run_with_custom_policy()
    policy_tips()
    few_shot_examples()
    
    print("\n" + "="*60)
    print("Custom policies make LLM classification accurate and safe!")
    print("="*60 + "\n")
