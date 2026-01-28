"""Triage engine with safety gates for DataAtelier."""

from datetime import datetime, timedelta
from typing import Optional
import re

from .models import BlobMetadata, TriageDecision
from .llm import BaseLLMClient, build_triage_prompt, parse_llm_response
from .policy import load_policy, get_policy_version, load_few_shot_examples, get_examples_version


# Keywords that trigger the NEVER DELETE gate
NEVER_DELETE_KEYWORDS = [
    'legal', 'contract', 'agreement', 'compliance', 'audit',
    'pii', 'personal', 'gdpr', 'privacy', 'sensitive',
    'invoice', 'receipt', 'financial', 'payment',
    'master', 'source', 'original', 'backup',
    'production', 'prod', 'live'
]

# Folder patterns that suggest retention
RETENTION_FOLDERS = [
    'keep', 'preserve', 'archive', 'backup', 'retention'
]


def check_confidence_gate(confidence: float, threshold: float = 0.95) -> bool:
    """Check if confidence meets the minimum threshold.
    
    Gate 1: Confidence threshold - only auto-label if confidence is high enough.
    
    Args:
        confidence: Confidence score from LLM (0.0 to 1.0)
        threshold: Minimum confidence required (default 0.95)
        
    Returns:
        True if confidence meets threshold, False otherwise
    """
    return confidence >= threshold


def check_self_consistency_gate(
    decisions: list[TriageDecision],
    min_agreement: float = 1.0
) -> tuple[bool, Optional[TriageDecision]]:
    """Check if multiple LLM runs agree on the decision.
    
    Gate 2: Self-consistency - multiple independent runs must agree.
    
    Args:
        decisions: List of TriageDecision objects from multiple runs
        min_agreement: Minimum fraction of decisions that must agree (default 1.0 = all must agree)
        
    Returns:
        Tuple of (passes_gate, agreed_decision)
        - passes_gate: True if agreement threshold is met
        - agreed_decision: The decision that was agreed upon, or None if no agreement
    """
    if not decisions:
        return False, None
    
    # Count votes for each label
    votes = {}
    for decision in decisions:
        label = decision.label
        if label not in votes:
            votes[label] = []
        votes[label].append(decision)
    
    # Find the label with the most votes
    max_votes = max(len(v) for v in votes.values())
    majority_label = [label for label, v in votes.items() if len(v) == max_votes][0]
    
    # Check if agreement threshold is met
    agreement_fraction = max_votes / len(decisions)
    
    if agreement_fraction >= min_agreement:
        # Use the decision with highest confidence from the majority
        majority_decisions = votes[majority_label]
        best_decision = max(majority_decisions, key=lambda d: d.confidence)
        return True, best_decision
    
    return False, None


def check_never_delete_gate(metadata: dict, decision: TriageDecision) -> bool:
    """Check if the decision violates NEVER DELETE constraints.
    
    Gate 3: NEVER DELETE - check for keywords, recent activity, and retention signals.
    
    Args:
        metadata: Dictionary with blob metadata (name, path, last_modified, etc.)
        decision: The triage decision to check
        
    Returns:
        True if the decision passes the gate (safe to proceed), False if it violates NEVER DELETE
    """
    # Only apply this gate to delete decisions
    if decision.label != 'delete':
        return True
    
    blob_name = metadata.get('name', '').lower()
    blob_path = metadata.get('path', '').lower()
    
    # Check 1: Keywords in name or path
    for keyword in NEVER_DELETE_KEYWORDS:
        if keyword in blob_name or keyword in blob_path:
            return False
    
    # Check 2: Retention folder patterns
    for folder in RETENTION_FOLDERS:
        if f'/{folder}/' in blob_path or blob_path.startswith(f'{folder}/'):
            return False
    
    # Check 3: Recent activity (last 7 days)
    last_modified = metadata.get('last_modified')
    if last_modified:
        try:
            # Handle both datetime objects and ISO strings
            if isinstance(last_modified, str):
                last_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            
            cutoff = datetime.now(last_modified.tzinfo) - timedelta(days=7)
            if last_modified > cutoff:
                return False
        except (ValueError, TypeError):
            # If we can't parse the date, be conservative and reject
            return False
    
    # All checks passed
    return True


def triage_blob(
    config,
    blob: BlobMetadata,
    llm_client: BaseLLMClient,
    policy_text: Optional[str] = None,
    examples: Optional[list] = None
) -> TriageDecision:
    """Triage a single blob with all safety gates.
    
    Args:
        config: Configuration object with triage settings
        blob: BlobMetadata object to triage
        llm_client: LLM client instance
        policy_text: Optional policy text (loaded from file if not provided)
        examples: Optional list of examples (loaded from file if not provided)
        
    Returns:
        TriageDecision for the blob
    """
    # Load policy and examples if not provided
    if policy_text is None:
        policy_text = load_policy(config.policy_file)
    
    if examples is None:
        examples = load_few_shot_examples(config.few_shot_file, max_examples=5)
    
    # Get policy and examples versions
    policy_version = get_policy_version(config.policy_file)
    examples_version = get_examples_version(config.few_shot_file)
    
    # Prepare metadata dictionary
    metadata = blob.to_dict()
    
    # Run multiple LLM calls for self-consistency
    decisions = []
    for i in range(config.self_consistency_runs):
        # Use temperature > 0 for diversity in self-consistency runs
        temperature = 0.0 if config.self_consistency_runs == 1 else 0.3
        
        # Build prompt
        prompt = build_triage_prompt(
            metadata=metadata,
            preview=blob.preview,
            policy=policy_text,
            examples=examples
        )
        
        try:
            # Call LLM
            response = llm_client.call(prompt, temperature=temperature)
            
            # Parse response
            parsed = parse_llm_response(response)
            
            # Create decision object
            decision = TriageDecision(
                label=parsed['label'],
                confidence=parsed['confidence'],
                reason=parsed['reason'],
                policy_version=policy_version,
                examples_version=examples_version
            )
            
            decisions.append(decision)
            
        except Exception as e:
            # If LLM call fails, create a human_review decision
            decisions.append(TriageDecision(
                label='human_review',
                confidence=0.0,
                reason=f'LLM call failed: {str(e)}',
                policy_version=policy_version,
                examples_version=examples_version
            ))
    
    # Gate 2: Self-consistency check
    passes_consistency, agreed_decision = check_self_consistency_gate(
        decisions,
        min_agreement=1.0  # All runs must agree
    )
    
    if not passes_consistency or agreed_decision is None:
        # No agreement - route to human review
        return TriageDecision(
            label='human_review',
            confidence=0.0,
            reason='Self-consistency check failed: LLM runs did not agree',
            policy_version=policy_version,
            examples_version=examples_version
        )
    
    # Gate 1: Confidence threshold check
    if not check_confidence_gate(agreed_decision.confidence, config.confidence_threshold):
        # Confidence too low - route to human review
        return TriageDecision(
            label='human_review',
            confidence=agreed_decision.confidence,
            reason=f'Confidence {agreed_decision.confidence:.2f} below threshold {config.confidence_threshold:.2f}',
            policy_version=policy_version,
            examples_version=examples_version
        )
    
    # Gate 3: NEVER DELETE check
    if not check_never_delete_gate(metadata, agreed_decision):
        # Violates NEVER DELETE constraints
        return TriageDecision(
            label='human_review',
            confidence=0.0,
            reason='NEVER DELETE gate triggered: blob matches protected patterns or has recent activity',
            policy_version=policy_version,
            examples_version=examples_version
        )
    
    # All gates passed - return the agreed decision
    return agreed_decision


def batch_triage(
    config,
    blobs: list[BlobMetadata],
    llm_client: BaseLLMClient
) -> list[TriageDecision]:
    """Triage multiple blobs in batch.
    
    Args:
        config: Configuration object with triage settings
        blobs: List of BlobMetadata objects to triage
        llm_client: LLM client instance
        
    Returns:
        List of TriageDecision objects (one per blob)
    """
    # Load policy and examples once for efficiency
    policy_text = load_policy(config.policy_file)
    examples = load_few_shot_examples(config.few_shot_file, max_examples=5)
    
    decisions = []
    
    for blob in blobs:
        decision = triage_blob(
            config=config,
            blob=blob,
            llm_client=llm_client,
            policy_text=policy_text,
            examples=examples
        )
        decisions.append(decision)
    
    return decisions
