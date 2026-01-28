"""LLM-based triage for blob classification."""

import hashlib
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from openai import OpenAI, AzureOpenAI

logger = logging.getLogger(__name__)


class TriageLLM:
    """LLM-powered conservative classifier for blob cleanup."""

    def __init__(
        self,
        model: str = "gpt-4",
        confidence_threshold: float = 0.95,
        self_consistency_passes: int = 3,
        temperature: float = 0.0,
        use_azure: bool = False,
    ):
        """Initialize LLM triage.
        
        Args:
            model: Model name (e.g., "gpt-4", "gpt-3.5-turbo")
            confidence_threshold: Minimum confidence for auto-accept
            self_consistency_passes: Number of passes for self-consistency check
            temperature: Sampling temperature (0.0 for deterministic)
            use_azure: Whether to use Azure OpenAI
        """
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.self_consistency_passes = self_consistency_passes
        self.temperature = temperature
        
        # Initialize client
        if use_azure:
            self.client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            )
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # System prompt
        self.system_prompt = """You are a conservative file classification assistant for Azure Blob Storage cleanup.

Your task is to classify files as either 'keep', 'delete', or 'human_review'.

KEY RULES:
1. Return ONLY valid JSON with fields: label, confidence (0-1), reason
2. Prefer 'human_review' unless you are COMPLETELY certain
3. Respect all "never-delete" clauses from the policy
4. Consider file age, path, type, and content
5. Be conservative: when in doubt, use 'human_review'

OUTPUT FORMAT (strict JSON only):
{
  "label": "keep" | "delete" | "human_review",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}"""

    def build_prompt(
        self,
        policy: str,
        few_shot_examples: str,
        blob_metadata: Dict,
        preview_text: str,
    ) -> str:
        """Build user prompt for classification.
        
        Args:
            policy: Policy text (summarized)
            few_shot_examples: Formatted examples
            blob_metadata: Blob metadata dict
            preview_text: Preview of content
            
        Returns:
            User prompt string
        """
        prompt_parts = [
            "# Classification Task",
            "",
            "## Policy/Rubric",
            policy,
            "",
            few_shot_examples,
            "",
            "## File to Classify",
            "Metadata:",
            f"- Name: {blob_metadata.get('name', 'unknown')}",
            f"- Container: {blob_metadata.get('container', 'unknown')}",
            f"- Size: {blob_metadata.get('size', 'unknown')} bytes",
            f"- Last Modified: {blob_metadata.get('last_modified', 'unknown')}",
            f"- Content Type: {blob_metadata.get('content_type', 'unknown')}",
            "",
        ]
        
        if preview_text and preview_text != "[Binary content]":
            # Limit preview length
            preview = preview_text[:2000]
            if len(preview_text) > 2000:
                preview += "\n... [truncated]"
            prompt_parts.extend([
                "Content Preview:",
                "```",
                preview,
                "```",
                "",
            ])
        else:
            prompt_parts.append("Content: [Binary or no preview available]")
            prompt_parts.append("")
        
        prompt_parts.extend([
            "## Your Task",
            "Classify this file as 'keep', 'delete', or 'human_review'.",
            "Output ONLY valid JSON with: label, confidence, reason",
        ])
        
        return "\n".join(prompt_parts)

    def classify(
        self,
        policy: str,
        few_shot_examples: str,
        blob_metadata: Dict,
        preview_text: str,
    ) -> Dict:
        """Classify a blob using LLM.
        
        Args:
            policy: Policy text
            few_shot_examples: Formatted examples
            blob_metadata: Blob metadata
            preview_text: Preview text
            
        Returns:
            Classification dict with label, confidence, reason, passes_self_consistency
        """
        prompt = self.build_prompt(policy, few_shot_examples, blob_metadata, preview_text)
        
        # Get single prediction
        prediction = self._call_llm(prompt)
        if not prediction:
            return {
                "label": "human_review",
                "confidence": 0.0,
                "reason": "LLM call failed",
                "passes_self_consistency": False,
            }
        
        # Self-consistency check
        passes_sc = self._self_consistency_check(prompt, prediction)
        prediction["passes_self_consistency"] = passes_sc
        
        # Apply certainty gates
        final_label = self._apply_certainty_gates(prediction, policy)
        prediction["label"] = final_label
        
        return prediction

    def _call_llm(self, prompt: str, retries: int = 3) -> Optional[Dict]:
        """Call LLM and parse JSON response.
        
        Args:
            prompt: User prompt
            retries: Number of retries for parsing failures
            
        Returns:
            Parsed response dict or None
        """
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=500,
                )
                
                content = response.choices[0].message.content.strip()
                
                # Try to parse JSON
                try:
                    result = json.loads(content)
                    # Validate fields
                    if "label" in result and "confidence" in result and "reason" in result:
                        return result
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    if "```" in content:
                        json_str = content.split("```")[1]
                        if json_str.startswith("json"):
                            json_str = json_str[4:]
                        result = json.loads(json_str.strip())
                        if "label" in result and "confidence" in result and "reason" in result:
                            return result
                
                # Retry with stricter instruction
                if attempt < retries - 1:
                    prompt += "\n\nIMPORTANT: Output ONLY valid JSON, no markdown, no explanation."
                
            except Exception as e:
                logger.error(f"LLM call error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
        
        return None

    def _self_consistency_check(self, prompt: str, prediction: Dict) -> bool:
        """Check if multiple LLM calls agree on the label.
        
        Note: Self-consistency is most effective when temperature > 0 to get varied responses.
        With temperature=0, this provides verification through redundant calls.
        
        Args:
            prompt: User prompt
            prediction: Initial prediction
            
        Returns:
            True if self-consistent
        """
        if self.self_consistency_passes <= 1:
            return True
        
        original_label = prediction.get("label")
        if original_label == "human_review":
            return True  # No need to verify uncertainty
        
        # Make additional calls
        for _ in range(self.self_consistency_passes - 1):
            result = self._call_llm(prompt)
            if not result or result.get("label") != original_label:
                return False
        
        return True

    def _apply_certainty_gates(self, prediction: Dict, policy: str) -> str:
        """Apply certainty gates to determine final label.
        
        Args:
            prediction: LLM prediction
            policy: Policy text
            
        Returns:
            Final label (keep, delete, or human_review)
        """
        label = prediction.get("label", "human_review")
        confidence = prediction.get("confidence", 0.0)
        reason = prediction.get("reason", "")
        passes_sc = prediction.get("passes_self_consistency", False)
        
        # If already human_review, keep it
        if label == "human_review":
            return "human_review"
        
        # Check confidence threshold
        if confidence < self.confidence_threshold:
            return "human_review"
        
        # Check self-consistency
        if not passes_sc:
            return "human_review"
        
        # Check policy alignment (never-delete clauses)
        if label == "delete" and self._violates_never_delete(reason, policy):
            return "human_review"
        
        return label

    def _violates_never_delete(self, reason: str, policy: str) -> bool:
        """Check if a delete decision might violate never-delete clauses.
        
        Args:
            reason: Reason for deletion
            policy: Policy text
            
        Returns:
            True if potential violation detected
        """
        # Extract never-delete section from policy
        never_delete_keywords = [
            "customer", "production", "prod", "live", "backup",
            "pii", "personal", "sensitive", "compliance", "legal"
        ]
        
        reason_lower = reason.lower()
        for keyword in never_delete_keywords:
            if keyword in reason_lower:
                logger.warning(f"Potential never-delete violation: {keyword} in reason")
                return True
        
        return False

    def batch_classify(
        self,
        policy: str,
        few_shot_examples: str,
        blobs: List[Dict],
        rate_limit_delay: float = 1.0,
    ) -> List[Dict]:
        """Classify multiple blobs with rate limiting.
        
        Args:
            policy: Policy text
            few_shot_examples: Formatted examples
            blobs: List of blob dicts with metadata and preview_text
            rate_limit_delay: Delay between calls in seconds (default 1.0 for safety)
            
        Returns:
            List of classification results
        """
        results = []
        for i, blob in enumerate(blobs):
            logger.info(f"Classifying blob {i + 1}/{len(blobs)}: {blob.get('name', 'unknown')}")
            
            result = self.classify(
                policy,
                few_shot_examples,
                blob,
                blob.get("preview_text", ""),
            )
            
            # Add metadata
            result["url"] = blob.get("url", "")
            result["container"] = blob.get("container", "")
            result["name"] = blob.get("name", "")
            
            results.append(result)
            
            # Rate limiting
            if i < len(blobs) - 1:
                time.sleep(rate_limit_delay)
        
        return results

    def get_cache_key(
        self,
        blob_url: str,
        policy_version: str,
        examples_version: str,
        snippet_hash: str,
    ) -> str:
        """Generate cache key for a classification.
        
        Args:
            blob_url: Blob URL
            policy_version: Policy version hash
            examples_version: Examples version hash
            snippet_hash: Hash of preview snippet
            
        Returns:
            Cache key string
        """
        key_parts = [
            blob_url,
            policy_version,
            examples_version,
            snippet_hash,
            self.model,
        ]
        combined = "|".join(key_parts)
        return hashlib.sha256(combined.encode()).hexdigest()
