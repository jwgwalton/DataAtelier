"""Policy file management and versioning."""

import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


DEFAULT_POLICY = """# Azure Blob Storage Cleanup Policy

## Purpose and Scope
This policy guides the classification of Azure Blob Storage files for cleanup.
Files are classified as either **keep** or **delete** based on the criteria below.

## Positive Signals for DELETE
Files that should be deleted include:
- Temporary files (`.tmp`, `.temp`, `.bak`, `.old`)
- Build artifacts (`.o`, `.pyc`, `.class`, compiled binaries)
- Log files older than 90 days
- Cache files and directories
- Duplicate or redundant data
- Test data that is no longer needed
- Empty or near-empty files (< 10 bytes)
- Files with "test", "temp", "draft", "old" in the path

## Positive Signals for KEEP
Files that should be kept include:
- Source code (`.py`, `.java`, `.js`, `.c`, `.cpp`, etc.)
- Configuration files (`.json`, `.yaml`, `.xml`, `.ini`, `.conf`)
- Documentation (`.md`, `.txt`, `.pdf`, `.docx`)
- Production data and datasets
- Customer data or sensitive information
- Recent log files (< 90 days)
- Files in paths containing "prod", "production", "main", "master"

## Never-Delete Clauses (Guardrails)
**NEVER** delete files that:
1. Contain customer data or personally identifiable information (PII)
2. Are in production paths (`/prod/`, `/production/`, `/live/`)
3. Are configuration files for active systems
4. Are recent (< 7 days old) unless clearly temporary
5. Have "backup" in the path
6. Are legal or compliance-related documents

## Edge Cases and Guidance
- If uncertain about a file's purpose, classify as `human_review`
- Large files (> 100 MB) should be reviewed by humans unless clearly temporary
- Files without extensions should be reviewed
- Files in unusual locations should be reviewed
- When confidence is below 95%, classify as `human_review`

## Examples of Borderline Cases
- **Log rotation files**: Keep if recent (< 30 days), delete if older
- **Snapshot files**: Review to determine if still needed
- **Data exports**: Review to verify if still relevant
- **Cache with timestamps**: Delete if older than cache TTL (usually 7-30 days)
"""


class PolicyManager:
    """Manages the LLM policy file."""

    def __init__(self, policy_path: Path):
        """Initialize policy manager.
        
        Args:
            policy_path: Path to policy markdown file
        """
        self.policy_path = policy_path
        self._ensure_policy_exists()

    def _ensure_policy_exists(self) -> None:
        """Create default policy if it doesn't exist."""
        if not self.policy_path.exists():
            self.write_policy(DEFAULT_POLICY)
            logger.info(f"Created default policy at {self.policy_path}")

    def read_policy(self) -> str:
        """Read the current policy.
        
        Returns:
            Policy text
        """
        try:
            return self.policy_path.read_text()
        except Exception as e:
            logger.error(f"Error reading policy: {e}")
            return DEFAULT_POLICY

    def write_policy(self, content: str) -> None:
        """Write policy content.
        
        Args:
            content: Policy markdown text
        """
        try:
            self.policy_path.write_text(content)
            logger.info(f"Updated policy at {self.policy_path}")
        except Exception as e:
            logger.error(f"Error writing policy: {e}")

    def get_version(self) -> str:
        """Get policy version (hash).
        
        Returns:
            Hash string
        """
        content = self.read_policy()
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def open_in_editor(self, editor: Optional[str] = None) -> bool:
        """Open policy in external editor.
        
        Args:
            editor: Editor command (uses $EDITOR if not specified)
            
        Returns:
            True if editor exited successfully
        """
        import os
        import subprocess
        
        if editor is None:
            editor = os.environ.get("EDITOR", "nano")
        
        try:
            result = subprocess.run([editor, str(self.policy_path)])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error opening editor: {e}")
            return False

    def summarize(self, max_length: int = 2000) -> str:
        """Get a summarized version of the policy for prompts.
        
        Args:
            max_length: Maximum length of summary
            
        Returns:
            Summarized policy text
        """
        content = self.read_policy()
        if len(content) <= max_length:
            return content
        
        # Extract key sections
        lines = content.split("\n")
        summary_lines = []
        in_important_section = False
        
        for line in lines:
            # Keep headers
            if line.startswith("#"):
                summary_lines.append(line)
                in_important_section = True
            # Keep important bullets
            elif line.strip().startswith("-") or line.strip().startswith("*"):
                if in_important_section:
                    summary_lines.append(line)
            # Keep numbered items
            elif line.strip() and line.strip()[0].isdigit() and "." in line[:3]:
                summary_lines.append(line)
            # Skip long paragraphs
            elif not line.strip():
                in_important_section = False
        
        summary = "\n".join(summary_lines)
        if len(summary) > max_length:
            summary = summary[:max_length] + "\n..."
        
        return summary
