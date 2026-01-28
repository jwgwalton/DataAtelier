"""Few-shot examples management (JSONL format)."""

import hashlib
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExamplesManager:
    """Manages few-shot examples in JSONL format."""

    def __init__(self, examples_path: Path):
        """Initialize examples manager.
        
        Args:
            examples_path: Path to examples JSONL file
        """
        self.examples_path = examples_path
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create empty JSONL file if it doesn't exist."""
        if not self.examples_path.exists():
            self.examples_path.touch()
            logger.info(f"Created examples file at {self.examples_path}")

    def read_examples(self) -> List[Dict]:
        """Read all examples from JSONL.
        
        Returns:
            List of example dictionaries
        """
        if not self.examples_path.exists():
            return []
        
        examples = []
        try:
            with open(self.examples_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        examples.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading examples: {e}")
        
        return examples

    def append_example(self, example: Dict) -> None:
        """Append a new example to JSONL.
        
        Args:
            example: Example dictionary with required fields:
                - label: "keep" or "delete"
                - reason: str
                - excerpt: str (preview text, optionally masked)
                - Optional: cues, path_hint, content_type, reviewer
        """
        # Validate required fields
        if "label" not in example or example["label"] not in ["keep", "delete"]:
            raise ValueError("Example must have 'label' field with value 'keep' or 'delete'")
        if "reason" not in example:
            raise ValueError("Example must have 'reason' field")
        if "excerpt" not in example:
            example["excerpt"] = ""
        
        # Add metadata
        if "decided_at" not in example:
            example["decided_at"] = datetime.utcnow().isoformat()
        
        # Write to file
        try:
            with open(self.examples_path, "a") as f:
                f.write(json.dumps(example) + "\n")
            logger.info(f"Added example with label '{example['label']}'")
        except Exception as e:
            logger.error(f"Error appending example: {e}")

    def get_balanced_sample(
        self,
        n: int = 8,
        label_balance: bool = True,
    ) -> List[Dict]:
        """Get a sample of examples, optionally balanced by label.
        
        Args:
            n: Number of examples to return
            label_balance: Whether to balance keep/delete examples
            
        Returns:
            List of sampled examples
        """
        examples = self.read_examples()
        if not examples:
            return []
        
        if len(examples) <= n:
            return examples
        
        if label_balance:
            # Split by label
            keep_examples = [ex for ex in examples if ex.get("label") == "keep"]
            delete_examples = [ex for ex in examples if ex.get("label") == "delete"]
            
            # Sample from each
            n_keep = min(n // 2, len(keep_examples))
            n_delete = min(n - n_keep, len(delete_examples))
            
            # Adjust if one category is smaller
            if n_delete < n // 2 and len(keep_examples) > n_keep:
                n_keep = min(n - n_delete, len(keep_examples))
            elif n_keep < n // 2 and len(delete_examples) > n_delete:
                n_delete = min(n - n_keep, len(delete_examples))
            
            sampled = []
            if keep_examples:
                sampled.extend(random.sample(keep_examples, n_keep))
            if delete_examples:
                sampled.extend(random.sample(delete_examples, n_delete))
            
            # Shuffle
            random.shuffle(sampled)
            return sampled
        else:
            return random.sample(examples, n)

    def get_version(self) -> str:
        """Get examples version (hash).
        
        Returns:
            Hash string
        """
        if not self.examples_path.exists():
            return "none"
        
        try:
            content = self.examples_path.read_text()
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception as e:
            logger.error(f"Error reading examples for version: {e}")
            return "error"

    def count_by_label(self) -> Dict[str, int]:
        """Count examples by label.
        
        Returns:
            Dictionary mapping label to count
        """
        examples = self.read_examples()
        counts = {"keep": 0, "delete": 0}
        for ex in examples:
            label = ex.get("label")
            if label in counts:
                counts[label] += 1
        return counts

    def clear(self) -> None:
        """Clear all examples (delete file and recreate empty)."""
        try:
            if self.examples_path.exists():
                self.examples_path.unlink()
            self._ensure_file_exists()
            logger.info("Cleared all examples")
        except Exception as e:
            logger.error(f"Error clearing examples: {e}")

    def format_for_prompt(self, examples: Optional[List[Dict]] = None) -> str:
        """Format examples for inclusion in LLM prompt.
        
        Args:
            examples: List of examples (uses sample if not provided)
            
        Returns:
            Formatted string for prompt
        """
        if examples is None:
            examples = self.get_balanced_sample()
        
        if not examples:
            return "No examples available yet."
        
        lines = ["## Few-Shot Examples:"]
        for i, ex in enumerate(examples, 1):
            label = ex.get("label", "unknown")
            reason = ex.get("reason", "")
            excerpt = ex.get("excerpt", "")[:500]  # Limit excerpt length
            
            lines.append(f"\n### Example {i}: {label.upper()}")
            lines.append(f"Reason: {reason}")
            if excerpt:
                lines.append(f"Excerpt: {excerpt}...")
            if "cues" in ex and ex["cues"]:
                lines.append(f"Key cues: {', '.join(ex['cues'])}")
        
        return "\n".join(lines)
