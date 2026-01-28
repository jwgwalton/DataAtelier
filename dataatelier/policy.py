"""Policy and examples management for DataAtelier."""

import hashlib
import json
from pathlib import Path
from typing import Optional
import random

from .models import FewShotExample


def load_policy(file_path: str) -> str:
    """Load policy document from file.
    
    Args:
        file_path: Path to policy markdown file
        
    Returns:
        Policy content as string
        
    Raises:
        FileNotFoundError: If policy file doesn't exist
        IOError: If file cannot be read
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {file_path}")
    
    try:
        return path.read_text(encoding='utf-8')
    except Exception as e:
        raise IOError(f"Failed to read policy file '{file_path}': {e}") from e


def get_policy_version(file_path: str) -> str:
    """Get version hash of policy file (MD5).
    
    Args:
        file_path: Path to policy markdown file
        
    Returns:
        MD5 hash of policy content (hex digest)
        
    Raises:
        FileNotFoundError: If policy file doesn't exist
        IOError: If file cannot be read
    """
    content = load_policy(file_path)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def load_few_shot_examples(
    file_path: str,
    max_examples: int = -1,
    balance: bool = True
) -> list[FewShotExample]:
    """Load few-shot learning examples from JSONL file.
    
    Args:
        file_path: Path to JSONL file with examples
        max_examples: Maximum number of examples to load (-1 for all)
        balance: Whether to balance examples across labels
        
    Returns:
        List of FewShotExample objects
        
    Raises:
        FileNotFoundError: If examples file doesn't exist
        IOError: If file cannot be read
        ValueError: If JSONL is malformed
    """
    path = Path(file_path)
    
    if not path.exists():
        # Return empty list if file doesn't exist yet
        return []
    
    try:
        examples = []
        
        with path.open('r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    example = FewShotExample(
                        label=data['label'],
                        reason=data['reason'],
                        excerpt=data['excerpt'],
                        path_hint=data['path_hint'],
                        content_type=data['content_type'],
                        date=data['date'],
                        reviewer=data['reviewer'],
                        cues=data.get('cues'),
                    )
                    examples.append(example)
                except (json.JSONDecodeError, KeyError) as e:
                    raise ValueError(f"Invalid JSON at line {line_num}: {e}") from e
        
        # Balance examples if requested
        if balance and examples:
            examples = _balance_examples(examples, max_examples)
        elif max_examples > 0 and len(examples) > max_examples:
            examples = examples[:max_examples]
        
        return examples
        
    except Exception as e:
        if isinstance(e, (FileNotFoundError, ValueError)):
            raise
        raise IOError(f"Failed to read examples file '{file_path}': {e}") from e


def _balance_examples(examples: list[FewShotExample], max_examples: int) -> list[FewShotExample]:
    """Balance examples across labels.
    
    Args:
        examples: List of all examples
        max_examples: Maximum total examples to return (-1 for all)
        
    Returns:
        Balanced list of examples
    """
    # Group by label
    by_label = {}
    for ex in examples:
        if ex.label not in by_label:
            by_label[ex.label] = []
        by_label[ex.label].append(ex)
    
    if not by_label:
        return []
    
    # If max_examples is -1, use all examples with balanced sampling
    if max_examples <= 0:
        max_examples = len(examples)
    
    # Calculate examples per label
    num_labels = len(by_label)
    per_label = max_examples // num_labels
    remainder = max_examples % num_labels
    
    balanced = []
    
    for i, (label, label_examples) in enumerate(sorted(by_label.items())):
        # Distribute remainder across first few labels
        count = per_label + (1 if i < remainder else 0)
        
        # Sample or take all if fewer than count
        if len(label_examples) <= count:
            balanced.extend(label_examples)
        else:
            balanced.extend(random.sample(label_examples, count))
    
    # Shuffle to mix labels
    random.shuffle(balanced)
    
    return balanced


def get_examples_version(file_path: str) -> str:
    """Get version hash of examples file (MD5).
    
    Args:
        file_path: Path to JSONL examples file
        
    Returns:
        MD5 hash of examples content (hex digest), or empty string if file doesn't exist
    """
    path = Path(file_path)
    
    if not path.exists():
        return ""
    
    try:
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()
    except Exception:
        return ""


def save_few_shot_example(file_path: str, example: FewShotExample) -> None:
    """Append a few-shot example to JSONL file.
    
    Args:
        file_path: Path to JSONL examples file
        example: FewShotExample to save
        
    Raises:
        IOError: If file cannot be written
    """
    path = Path(file_path)
    
    try:
        # Create parent directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Append to file
        with path.open('a', encoding='utf-8') as f:
            json_line = json.dumps(example.to_dict(), ensure_ascii=False)
            f.write(json_line + '\n')
            
    except Exception as e:
        raise IOError(f"Failed to save example to '{file_path}': {e}") from e
