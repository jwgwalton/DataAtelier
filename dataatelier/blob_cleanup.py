"""
Azure Blob Storage Cleanup Tool with LLM-based Triage

This module provides a comprehensive solution for managing Azure Blob Storage cleanup
with conservative LLM-based decision making, human review interface, and full audit trail.

Key Features:
- Conservative LLM triage (confidence ≥0.95, self-consistency, policy alignment)
- Support for multiple LLM providers (OpenAI, Azure OpenAI, Ollama)
- Text extraction for various file types (txt, json, pdf, docx)
- Queue management (to_review.csv, to_delete.csv, to_keep.csv)
- Few-shot learning from human decisions
- Full audit trail with policy versioning
"""

import os
import io
import json
import logging
import hashlib
import csv
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Literal
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter
import time

# Azure Storage
from azure.storage.blob import BlobServiceClient, BlobProperties, ContainerClient
from azure.core.exceptions import AzureError, ResourceNotFoundError

# Data processing
import pandas as pd
from tqdm.auto import tqdm

# Text extraction
import chardet
from pdfminer.high_level import extract_text as extract_pdf_text
from docx import Document

# LLM integration
from openai import OpenAI, AzureOpenAI
import tiktoken

# Notebook UI
try:
    from IPython.display import display, HTML, clear_output
    import ipywidgets as widgets
    IPYWIDGETS_AVAILABLE = True
except ImportError:
    IPYWIDGETS_AVAILABLE = False

# Configuration
from dotenv import load_dotenv


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BlobCleanupConfig:
    """Configuration for Azure Blob Cleanup with environment variable support."""
    
    # Azure Storage
    connection_string: str
    container_name: str
    
    # LLM Provider settings
    llm_provider: Literal["openai", "azure_openai", "ollama"] = "openai"
    llm_model: str = "gpt-4"
    llm_api_key: Optional[str] = None
    llm_endpoint: Optional[str] = None  # For Azure OpenAI or Ollama
    llm_api_version: str = "2024-02-15-preview"  # For Azure OpenAI
    
    # Policy settings
    policy_file: str = "llm_policy.md"
    confidence_threshold: float = 0.95
    self_consistency_runs: int = 3
    
    # Queue files
    queue_dir: str = "cleanup_queues"
    to_review_csv: str = "to_review.csv"
    to_delete_csv: str = "to_delete.csv"
    to_keep_csv: str = "to_keep.csv"
    audit_log_csv: str = "audit_log.csv"
    
    # Text extraction limits
    max_preview_chars: int = 2000
    max_blob_size_for_preview: int = 10 * 1024 * 1024  # 10 MB
    
    # Token limits
    max_tokens_per_request: int = 8000
    
    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> 'BlobCleanupConfig':
        """Load configuration from environment variables."""
        if env_file and os.path.exists(env_file):
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        return cls(
            connection_string=os.getenv('AZURE_STORAGE_CONNECTION_STRING', ''),
            container_name=os.getenv('AZURE_CONTAINER_NAME', ''),
            llm_provider=os.getenv('LLM_PROVIDER', 'openai'),
            llm_model=os.getenv('LLM_MODEL', 'gpt-4'),
            llm_api_key=os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY'),
            llm_endpoint=os.getenv('LLM_ENDPOINT'),
            llm_api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),
            policy_file=os.getenv('POLICY_FILE', 'llm_policy.md'),
            confidence_threshold=float(os.getenv('CONFIDENCE_THRESHOLD', '0.95')),
            self_consistency_runs=int(os.getenv('SELF_CONSISTENCY_RUNS', '3')),
            queue_dir=os.getenv('QUEUE_DIR', 'cleanup_queues'),
            max_preview_chars=int(os.getenv('MAX_PREVIEW_CHARS', '2000')),
            max_blob_size_for_preview=int(os.getenv('MAX_BLOB_SIZE_MB', '10')) * 1024 * 1024,
        )
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if not self.connection_string:
            errors.append("AZURE_STORAGE_CONNECTION_STRING is required")
        
        if not self.container_name:
            errors.append("AZURE_CONTAINER_NAME is required")
        
        if not self.llm_api_key and self.llm_provider != "ollama":
            errors.append(f"LLM_API_KEY is required for provider: {self.llm_provider}")
        
        if self.llm_provider == "azure_openai" and not self.llm_endpoint:
            errors.append("LLM_ENDPOINT is required for Azure OpenAI")
        
        if not os.path.exists(self.policy_file):
            errors.append(f"Policy file not found: {self.policy_file}")
        
        if not 0 <= self.confidence_threshold <= 1:
            errors.append("Confidence threshold must be between 0 and 1")
        
        if self.self_consistency_runs < 1:
            errors.append("Self-consistency runs must be at least 1")
        
        return errors


@dataclass
class BlobMetadata:
    """Metadata for a blob with extracted preview."""
    
    name: str
    size: int
    last_modified: datetime
    content_type: str
    etag: str
    preview: str
    preview_error: Optional[str] = None
    metadata: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV/JSON serialization."""
        return {
            'name': self.name,
            'size': self.size,
            'last_modified': self.last_modified.isoformat(),
            'content_type': self.content_type,
            'etag': self.etag,
            'preview': self.preview,
            'preview_error': self.preview_error,
            'metadata': json.dumps(self.metadata or {}),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BlobMetadata':
        """Create from dictionary."""
        return cls(
            name=data['name'],
            size=int(data['size']),
            last_modified=datetime.fromisoformat(data['last_modified']),
            content_type=data['content_type'],
            etag=data['etag'],
            preview=data['preview'],
            preview_error=data.get('preview_error'),
            metadata=json.loads(data.get('metadata', '{}')),
        )


@dataclass
class TriageDecision:
    """LLM triage decision with confidence and reasoning."""
    
    blob_name: str
    decision: Literal["DELETE", "KEEP", "HUMAN_REVIEW"]
    confidence: float
    reasoning: str
    policy_hash: str
    timestamp: datetime
    llm_model: str
    self_consistency_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV/JSON serialization."""
        return {
            'blob_name': self.blob_name,
            'decision': self.decision,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'policy_hash': self.policy_hash,
            'timestamp': self.timestamp.isoformat(),
            'llm_model': self.llm_model,
            'self_consistency_score': self.self_consistency_score,
        }


class BlobInventory:
    """Handles blob listing, preview extraction, and manifest creation."""
    
    def __init__(self, config: BlobCleanupConfig):
        self.config = config
        self.blob_service_client = BlobServiceClient.from_connection_string(
            config.connection_string
        )
        self.container_client = self.blob_service_client.get_container_client(
            config.container_name
        )
    
    def list_blobs(self, prefix: Optional[str] = None) -> List[BlobProperties]:
        """List all blobs in container with optional prefix filter."""
        try:
            logger.info(f"Listing blobs in container: {self.config.container_name}")
            blobs = list(self.container_client.list_blobs(name_starts_with=prefix))
            logger.info(f"Found {len(blobs)} blobs")
            return blobs
        except AzureError as e:
            logger.error(f"Failed to list blobs: {e}")
            raise
    
    def extract_text_preview(self, blob_name: str) -> Tuple[str, Optional[str]]:
        """
        Extract text preview from blob based on file type.
        
        Returns:
            Tuple of (preview_text, error_message)
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            properties = blob_client.get_blob_properties()
            
            # Skip large files
            if properties.size > self.config.max_blob_size_for_preview:
                return f"[File too large for preview: {properties.size:,} bytes]", None
            
            # Download blob content
            blob_data = blob_client.download_blob().readall()
            
            # Determine file type and extract text
            file_ext = Path(blob_name).suffix.lower()
            
            if file_ext in ['.txt', '.log', '.md', '.csv', '.json', '.xml', '.html']:
                return self._extract_text_from_text_file(blob_data)
            elif file_ext == '.pdf':
                return self._extract_text_from_pdf(blob_data)
            elif file_ext in ['.docx', '.doc']:
                return self._extract_text_from_docx(blob_data)
            else:
                # Try to detect if it's text
                return self._extract_text_from_unknown(blob_data)
                
        except Exception as e:
            error_msg = f"Failed to extract preview: {str(e)}"
            logger.warning(f"Preview extraction failed for {blob_name}: {e}")
            return f"[Preview unavailable]", error_msg
    
    def _extract_text_from_text_file(self, data: bytes) -> Tuple[str, Optional[str]]:
        """Extract text from plain text files."""
        try:
            # Detect encoding
            detected = chardet.detect(data)
            encoding = detected.get('encoding', 'utf-8')
            
            # Decode with fallback
            try:
                text = data.decode(encoding)
            except (UnicodeDecodeError, TypeError):
                text = data.decode('utf-8', errors='replace')
            
            # Truncate to max preview length
            if len(text) > self.config.max_preview_chars:
                text = text[:self.config.max_preview_chars] + "\n...[truncated]"
            
            return text, None
            
        except Exception as e:
            return f"[Text extraction failed]", str(e)
    
    def _extract_text_from_pdf(self, data: bytes) -> Tuple[str, Optional[str]]:
        """Extract text from PDF files."""
        try:
            text = extract_pdf_text(io.BytesIO(data))
            
            if len(text) > self.config.max_preview_chars:
                text = text[:self.config.max_preview_chars] + "\n...[truncated]"
            
            return text, None
            
        except Exception as e:
            return f"[PDF extraction failed]", str(e)
    
    def _extract_text_from_docx(self, data: bytes) -> Tuple[str, Optional[str]]:
        """Extract text from DOCX files."""
        try:
            doc = Document(io.BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs]
            text = '\n'.join(paragraphs)
            
            if len(text) > self.config.max_preview_chars:
                text = text[:self.config.max_preview_chars] + "\n...[truncated]"
            
            return text, None
            
        except Exception as e:
            return f"[DOCX extraction failed]", str(e)
    
    def _extract_text_from_unknown(self, data: bytes) -> Tuple[str, Optional[str]]:
        """Try to extract text from unknown file types."""
        try:
            # Check if it looks like text
            detected = chardet.detect(data[:10000])  # Check first 10KB
            
            if detected.get('confidence', 0) > 0.7:
                encoding = detected.get('encoding', 'utf-8')
                text = data.decode(encoding, errors='replace')
                
                if len(text) > self.config.max_preview_chars:
                    text = text[:self.config.max_preview_chars] + "\n...[truncated]"
                
                return text, None
            else:
                return f"[Binary file, no preview available]", None
                
        except Exception as e:
            return f"[Unknown format]", str(e)
    
    def create_manifest(
        self, 
        prefix: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> List[BlobMetadata]:
        """
        Create inventory manifest with previews for all blobs.
        
        Args:
            prefix: Optional prefix filter for blob names
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of BlobMetadata objects
        """
        blobs = self.list_blobs(prefix)
        manifest = []
        
        iterator = tqdm(blobs, desc="Creating manifest") if not progress_callback else blobs
        
        for blob_props in iterator:
            preview, preview_error = self.extract_text_preview(blob_props.name)
            
            metadata = BlobMetadata(
                name=blob_props.name,
                size=blob_props.size,
                last_modified=blob_props.last_modified,
                content_type=blob_props.content_type or "application/octet-stream",
                etag=blob_props.etag,
                preview=preview,
                preview_error=preview_error,
                metadata=blob_props.metadata or {},
            )
            manifest.append(metadata)
            
            if progress_callback:
                progress_callback(len(manifest), len(blobs))
        
        logger.info(f"Created manifest with {len(manifest)} blobs")
        return manifest


class LLMTriageEngine:
    """LLM-based triage engine with conservative decision making."""
    
    def __init__(self, config: BlobCleanupConfig):
        self.config = config
        self.policy_text = self._load_policy()
        self.policy_hash = self._compute_policy_hash()
        self.client = self._initialize_llm_client()
        
        # Few-shot learning cache
        self.few_shot_examples: List[Dict[str, Any]] = []
    
    def _load_policy(self) -> str:
        """Load policy document."""
        try:
            with open(self.config.policy_file, 'r') as f:
                policy = f.read()
            logger.info(f"Loaded policy from {self.config.policy_file}")
            return policy
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")
            raise
    
    def _compute_policy_hash(self) -> str:
        """Compute MD5 hash of policy for versioning."""
        return hashlib.md5(self.policy_text.encode()).hexdigest()
    
    def _initialize_llm_client(self) -> Any:
        """Initialize LLM client based on provider."""
        if self.config.llm_provider == "openai":
            return OpenAI(api_key=self.config.llm_api_key)
        elif self.config.llm_provider == "azure_openai":
            return AzureOpenAI(
                api_key=self.config.llm_api_key,
                api_version=self.config.llm_api_version,
                azure_endpoint=self.config.llm_endpoint,
            )
        elif self.config.llm_provider == "ollama":
            return OpenAI(
                base_url=self.config.llm_endpoint or "http://localhost:11434/v1",
                api_key="ollama",  # Ollama doesn't require a real API key
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self.config.llm_provider}")
    
    def add_few_shot_example(self, blob_meta: BlobMetadata, decision: str, reasoning: str):
        """Add a human-reviewed example for few-shot learning."""
        example = {
            'blob_name': blob_meta.name,
            'size': blob_meta.size,
            'last_modified': blob_meta.last_modified.isoformat(),
            'preview': blob_meta.preview[:500],  # Keep examples short
            'decision': decision,
            'reasoning': reasoning,
        }
        self.few_shot_examples.append(example)
        logger.info(f"Added few-shot example: {blob_meta.name} -> {decision}")
    
    def _build_prompt(self, blob_meta: BlobMetadata) -> str:
        """Build prompt for LLM with policy and few-shot examples."""
        prompt_parts = [
            "# Azure Blob Storage Cleanup Decision Task",
            "",
            "You are an AI assistant helping to make conservative decisions about whether to delete, keep, or route to human review blobs in Azure Blob Storage.",
            "",
            "## Policy Document",
            "",
            self.policy_text,
            "",
            "## Your Task",
            "",
            "Analyze the blob information below and make a decision: DELETE, KEEP, or HUMAN_REVIEW.",
            "",
            "Requirements:",
            "- Be EXTREMELY conservative - when in doubt, choose HUMAN_REVIEW",
            "- Confidence must be ≥0.95 for automatic DELETE/KEEP decisions",
            "- Never violate NEVER DELETE constraints",
            "- Provide clear, specific reasoning",
            "",
        ]
        
        # Add few-shot examples if available
        if self.few_shot_examples:
            prompt_parts.extend([
                "## Examples from Human Decisions",
                "",
            ])
            
            for ex in self.few_shot_examples[-5:]:  # Last 5 examples
                prompt_parts.extend([
                    f"### Example: {ex['blob_name']}",
                    f"- Size: {ex['size']:,} bytes",
                    f"- Last Modified: {ex['last_modified']}",
                    f"- Preview: {ex['preview']}",
                    f"- Decision: {ex['decision']}",
                    f"- Reasoning: {ex['reasoning']}",
                    "",
                ])
        
        # Add blob to analyze
        prompt_parts.extend([
            "## Blob to Analyze",
            "",
            f"**Name:** {blob_meta.name}",
            f"**Size:** {blob_meta.size:,} bytes",
            f"**Last Modified:** {blob_meta.last_modified.isoformat()}",
            f"**Content Type:** {blob_meta.content_type}",
            "",
            "**Preview:**",
            "```",
            blob_meta.preview,
            "```",
            "",
            "## Response Format",
            "",
            "Respond ONLY with valid JSON in this exact format:",
            "{",
            '  "decision": "DELETE" | "KEEP" | "HUMAN_REVIEW",',
            '  "confidence": 0.0-1.0,',
            '  "reasoning": "Detailed explanation of decision"',
            "}",
        ])
        
        return "\n".join(prompt_parts)
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from LLM."""
        try:
            # Try to extract JSON from markdown code blocks if present
            if "```json" in response_text:
                start = response_text.index("```json") + 7
                end = response_text.index("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.index("```") + 3
                end = response_text.index("```", start)
                response_text = response_text[start:end].strip()
            
            data = json.loads(response_text)
            
            # Validate required fields
            required = ['decision', 'confidence', 'reasoning']
            for field in required:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate decision value
            if data['decision'] not in ['DELETE', 'KEEP', 'HUMAN_REVIEW']:
                raise ValueError(f"Invalid decision: {data['decision']}")
            
            # Validate confidence
            if not 0 <= data['confidence'] <= 1:
                raise ValueError(f"Confidence must be 0-1: {data['confidence']}")
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}\nResponse: {response_text}")
            raise
    
    def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Make a single call to LLM."""
        try:
            response = self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": "You are a conservative AI assistant for Azure Blob Storage cleanup decisions. Always prefer HUMAN_REVIEW when uncertain."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent decisions
                max_tokens=1000,
            )
            
            response_text = response.choices[0].message.content
            return self._parse_llm_response(response_text)
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _check_self_consistency(
        self, 
        blob_meta: BlobMetadata,
        num_runs: int = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Run multiple LLM calls and check for consistency.
        
        Returns:
            Tuple of (consensus_decision, consistency_score)
        """
        num_runs = num_runs or self.config.self_consistency_runs
        prompt = self._build_prompt(blob_meta)
        
        decisions = []
        for i in range(num_runs):
            try:
                result = self._call_llm(prompt)
                decisions.append(result)
                
                # Small delay between calls
                if i < num_runs - 1:
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.warning(f"Self-consistency run {i+1} failed: {e}")
                continue
        
        if not decisions:
            raise RuntimeError("All self-consistency runs failed")
        
        # Calculate consistency
        decision_values = [d['decision'] for d in decisions]
        decision_counts = Counter(decision_values)
        most_common_decision, count = decision_counts.most_common(1)[0]
        consistency_score = count / len(decisions)
        
        # Find the decision with highest confidence among consensus
        consensus_decisions = [d for d in decisions if d['decision'] == most_common_decision]
        best_decision = max(consensus_decisions, key=lambda x: x['confidence'])
        
        return best_decision, consistency_score
    
    def triage_blob(self, blob_meta: BlobMetadata) -> TriageDecision:
        """
        Perform conservative triage on a single blob.
        
        Applies multiple safety gates:
        1. Self-consistency check (multiple LLM runs must agree)
        2. Confidence threshold (≥0.95 for automatic decisions)
        3. Policy alignment check
        """
        try:
            # Run self-consistency check
            decision_data, consistency = self._check_self_consistency(blob_meta)
            
            # Apply conservative gates
            final_decision = decision_data['decision']
            confidence = decision_data['confidence']
            
            # Gate 1: Confidence threshold
            if confidence < self.config.confidence_threshold:
                final_decision = "HUMAN_REVIEW"
                decision_data['reasoning'] += f" [Low confidence: {confidence:.3f} < {self.config.confidence_threshold}]"
            
            # Gate 2: Self-consistency
            if consistency < 0.8:  # At least 80% agreement
                final_decision = "HUMAN_REVIEW"
                decision_data['reasoning'] += f" [Low consistency: {consistency:.3f}]"
            
            # Gate 3: Check for NEVER DELETE violations
            if final_decision == "DELETE":
                never_delete_keywords = [
                    'legal', 'compliance', 'audit', 'pii', 'personal',
                    'master', 'source', 'original', 'backup'
                ]
                blob_name_lower = blob_meta.name.lower()
                preview_lower = blob_meta.preview.lower()
                
                for keyword in never_delete_keywords:
                    if keyword in blob_name_lower or keyword in preview_lower:
                        final_decision = "HUMAN_REVIEW"
                        decision_data['reasoning'] += f" [Potential NEVER DELETE match: {keyword}]"
                        break
                
                # Check recent activity (last 7 days)
                if blob_meta.last_modified > datetime.now(timezone.utc) - timedelta(days=7):
                    final_decision = "HUMAN_REVIEW"
                    decision_data['reasoning'] += " [Recent activity: accessed within 7 days]"
            
            return TriageDecision(
                blob_name=blob_meta.name,
                decision=final_decision,
                confidence=confidence,
                reasoning=decision_data['reasoning'],
                policy_hash=self.policy_hash,
                timestamp=datetime.now(timezone.utc),
                llm_model=self.config.llm_model,
                self_consistency_score=consistency,
            )
            
        except Exception as e:
            logger.error(f"Triage failed for {blob_meta.name}: {e}")
            # On error, route to human review
            return TriageDecision(
                blob_name=blob_meta.name,
                decision="HUMAN_REVIEW",
                confidence=0.0,
                reasoning=f"Triage error: {str(e)}",
                policy_hash=self.policy_hash,
                timestamp=datetime.now(timezone.utc),
                llm_model=self.config.llm_model,
                self_consistency_score=0.0,
            )
    
    def batch_triage(
        self, 
        blobs: List[BlobMetadata],
        progress_callback: Optional[callable] = None
    ) -> List[TriageDecision]:
        """Triage multiple blobs with progress tracking."""
        decisions = []
        
        iterator = tqdm(blobs, desc="Triaging blobs") if not progress_callback else blobs
        
        for i, blob_meta in enumerate(iterator):
            decision = self.triage_blob(blob_meta)
            decisions.append(decision)
            
            if progress_callback:
                progress_callback(i + 1, len(blobs), decision)
            
            # Rate limiting
            time.sleep(0.5)
        
        logger.info(f"Completed triage for {len(decisions)} blobs")
        return decisions


class QueueManager:
    """Manages CSV queues for blobs awaiting review, deletion, or keeping."""
    
    def __init__(self, config: BlobCleanupConfig):
        self.config = config
        self.queue_dir = Path(config.queue_dir)
        self.queue_dir.mkdir(exist_ok=True, parents=True)
        
        self.to_review_path = self.queue_dir / config.to_review_csv
        self.to_delete_path = self.queue_dir / config.to_delete_csv
        self.to_keep_path = self.queue_dir / config.to_keep_csv
        self.audit_log_path = self.queue_dir / config.audit_log_csv
    
    def save_triage_decisions(
        self,
        blobs: List[BlobMetadata],
        decisions: List[TriageDecision]
    ):
        """Save triage decisions to appropriate queues."""
        # Create lookup for blob metadata
        blob_lookup = {b.name: b for b in blobs}
        
        # Separate by decision
        to_review = []
        to_delete = []
        to_keep = []
        
        for decision in decisions:
            blob_meta = blob_lookup.get(decision.blob_name)
            if not blob_meta:
                continue
            
            row = {
                **blob_meta.to_dict(),
                **decision.to_dict(),
            }
            
            if decision.decision == "HUMAN_REVIEW":
                to_review.append(row)
            elif decision.decision == "DELETE":
                to_delete.append(row)
            elif decision.decision == "KEEP":
                to_keep.append(row)
        
        # Save to CSV files
        if to_review:
            self._append_to_csv(self.to_review_path, to_review)
            logger.info(f"Added {len(to_review)} blobs to review queue")
        
        if to_delete:
            self._append_to_csv(self.to_delete_path, to_delete)
            logger.info(f"Added {len(to_delete)} blobs to delete queue")
        
        if to_keep:
            self._append_to_csv(self.to_keep_path, to_keep)
            logger.info(f"Added {len(to_keep)} blobs to keep queue")
    
    def _append_to_csv(self, path: Path, rows: List[Dict]):
        """Append rows to CSV file, creating it if needed."""
        write_header = not path.exists()
        
        with open(path, 'a', newline='', encoding='utf-8') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                if write_header:
                    writer.writeheader()
                writer.writerows(rows)
    
    def load_queue(self, queue_type: Literal["review", "delete", "keep"]) -> pd.DataFrame:
        """Load queue as pandas DataFrame."""
        path_map = {
            "review": self.to_review_path,
            "delete": self.to_delete_path,
            "keep": self.to_keep_path,
        }
        
        path = path_map[queue_type]
        if not path.exists():
            return pd.DataFrame()
        
        return pd.read_csv(path)
    
    def remove_from_queue(
        self,
        queue_type: Literal["review", "delete", "keep"],
        blob_names: List[str]
    ):
        """Remove blobs from queue."""
        df = self.load_queue(queue_type)
        if df.empty:
            return
        
        df = df[~df['name'].isin(blob_names)]
        
        path_map = {
            "review": self.to_review_path,
            "delete": self.to_delete_path,
            "keep": self.to_keep_path,
        }
        
        path = path_map[queue_type]
        df.to_csv(path, index=False)
    
    def log_audit_event(
        self,
        blob_name: str,
        action: str,
        user: str,
        reasoning: str,
        metadata: Optional[Dict] = None
    ):
        """Log audit event."""
        event = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'blob_name': blob_name,
            'action': action,
            'user': user,
            'reasoning': reasoning,
            'metadata': json.dumps(metadata or {}),
        }
        
        self._append_to_csv(self.audit_log_path, [event])


class ReviewUI:
    """Interactive review UI using ipywidgets."""
    
    def __init__(
        self,
        config: BlobCleanupConfig,
        queue_manager: QueueManager,
        llm_engine: Optional[LLMTriageEngine] = None
    ):
        if not IPYWIDGETS_AVAILABLE:
            raise ImportError("ipywidgets is required for ReviewUI")
        
        self.config = config
        self.queue_manager = queue_manager
        self.llm_engine = llm_engine
        
        self.current_index = 0
        self.review_data = []
        self.decisions = []  # Track user decisions for few-shot learning
    
    def load_review_queue(self):
        """Load blobs from review queue."""
        df = self.queue_manager.load_queue("review")
        if df.empty:
            logger.warning("No blobs in review queue")
            return
        
        self.review_data = df.to_dict('records')
        self.current_index = 0
        logger.info(f"Loaded {len(self.review_data)} blobs for review")
    
    def create_review_interface(self) -> widgets.VBox:
        """Create interactive review widget."""
        if not self.review_data:
            return widgets.VBox([
                widgets.HTML("<h3>No blobs to review</h3>")
            ])
        
        # Progress
        self.progress_label = widgets.HTML()
        
        # Blob information
        self.info_widget = widgets.HTML()
        
        # Preview
        self.preview_widget = widgets.Textarea(
            description='Preview:',
            disabled=True,
            layout=widgets.Layout(width='100%', height='300px')
        )
        
        # Decision buttons
        delete_btn = widgets.Button(
            description='🗑️ Delete',
            button_style='danger',
            layout=widgets.Layout(width='150px')
        )
        keep_btn = widgets.Button(
            description='✅ Keep',
            button_style='success',
            layout=widgets.Layout(width='150px')
        )
        skip_btn = widgets.Button(
            description='⏭️ Skip',
            button_style='info',
            layout=widgets.Layout(width='150px')
        )
        
        # Reasoning input
        self.reasoning_input = widgets.Textarea(
            description='Reasoning:',
            placeholder='Enter reasoning for your decision...',
            layout=widgets.Layout(width='100%', height='100px')
        )
        
        # Button actions
        delete_btn.on_click(lambda b: self._handle_decision('DELETE'))
        keep_btn.on_click(lambda b: self._handle_decision('KEEP'))
        skip_btn.on_click(lambda b: self._handle_skip())
        
        # Navigation
        prev_btn = widgets.Button(description='← Previous')
        next_btn = widgets.Button(description='Next →')
        prev_btn.on_click(lambda b: self._navigate(-1))
        next_btn.on_click(lambda b: self._navigate(1))
        
        # Layout
        button_box = widgets.HBox([delete_btn, keep_btn, skip_btn])
        nav_box = widgets.HBox([prev_btn, next_btn])
        
        interface = widgets.VBox([
            self.progress_label,
            widgets.HTML("<hr>"),
            self.info_widget,
            self.preview_widget,
            widgets.HTML("<hr>"),
            self.reasoning_input,
            button_box,
            nav_box,
        ])
        
        self._update_display()
        return interface
    
    def _update_display(self):
        """Update display with current blob."""
        if not self.review_data or self.current_index >= len(self.review_data):
            self.progress_label.value = "<h3>✅ Review Complete!</h3>"
            self.info_widget.value = ""
            self.preview_widget.value = ""
            return
        
        blob = self.review_data[self.current_index]
        
        # Progress
        progress = f"<h3>Reviewing Blob {self.current_index + 1} / {len(self.review_data)}</h3>"
        self.progress_label.value = progress
        
        # Info
        last_modified = datetime.fromisoformat(blob['last_modified'])
        info = f"""
        <h4>Blob Information</h4>
        <ul>
            <li><strong>Name:</strong> {blob['name']}</li>
            <li><strong>Size:</strong> {blob['size']:,} bytes</li>
            <li><strong>Last Modified:</strong> {last_modified.strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
            <li><strong>Content Type:</strong> {blob['content_type']}</li>
            <li><strong>LLM Decision:</strong> {blob.get('decision', 'N/A')}</li>
            <li><strong>LLM Confidence:</strong> {blob.get('confidence', 0):.2%}</li>
        </ul>
        <h4>LLM Reasoning</h4>
        <p>{blob.get('reasoning', 'N/A')}</p>
        """
        self.info_widget.value = info
        
        # Preview
        self.preview_widget.value = blob.get('preview', '[No preview available]')
        
        # Clear reasoning
        self.reasoning_input.value = ""
    
    def _handle_decision(self, decision: str):
        """Handle user decision."""
        if not self.review_data or self.current_index >= len(self.review_data):
            return
        
        blob = self.review_data[self.current_index]
        reasoning = self.reasoning_input.value or f"Human decision: {decision}"
        
        # Log audit event
        self.queue_manager.log_audit_event(
            blob_name=blob['name'],
            action=f"HUMAN_{decision}",
            user="human_reviewer",
            reasoning=reasoning,
        )
        
        # Move to appropriate queue
        self.queue_manager.remove_from_queue("review", [blob['name']])
        
        if decision == "DELETE":
            self.queue_manager._append_to_csv(
                self.queue_manager.to_delete_path,
                [blob]
            )
        elif decision == "KEEP":
            self.queue_manager._append_to_csv(
                self.queue_manager.to_keep_path,
                [blob]
            )
        
        # Add to few-shot learning
        if self.llm_engine:
            blob_meta = BlobMetadata.from_dict(blob)
            self.llm_engine.add_few_shot_example(blob_meta, decision, reasoning)
        
        # Track decision
        self.decisions.append({
            'blob_name': blob['name'],
            'decision': decision,
            'reasoning': reasoning,
        })
        
        # Move to next
        self._navigate(1)
    
    def _handle_skip(self):
        """Skip current blob."""
        self._navigate(1)
    
    def _navigate(self, direction: int):
        """Navigate to next/previous blob."""
        self.current_index += direction
        
        # Clamp to valid range
        self.current_index = max(0, min(self.current_index, len(self.review_data)))
        
        self._update_display()


class DeletionManager:
    """Handles dry-run and actual deletion with audit logging."""
    
    def __init__(
        self,
        config: BlobCleanupConfig,
        queue_manager: QueueManager
    ):
        self.config = config
        self.queue_manager = queue_manager
        self.blob_service_client = BlobServiceClient.from_connection_string(
            config.connection_string
        )
        self.container_client = self.blob_service_client.get_container_client(
            config.container_name
        )
    
    def dry_run(self) -> Dict[str, Any]:
        """
        Perform dry-run analysis of deletion queue.
        
        Returns:
            Dictionary with statistics and preview
        """
        df = self.queue_manager.load_queue("delete")
        
        if df.empty:
            return {
                'total_blobs': 0,
                'total_size_bytes': 0,
                'blobs': [],
            }
        
        total_size = df['size'].sum()
        
        return {
            'total_blobs': len(df),
            'total_size_bytes': int(total_size),
            'total_size_mb': total_size / (1024 * 1024),
            'total_size_gb': total_size / (1024 * 1024 * 1024),
            'blobs': df[['name', 'size', 'last_modified', 'reasoning']].to_dict('records'),
        }
    
    def execute_deletion(
        self,
        dry_run: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute blob deletion.
        
        Args:
            dry_run: If True, only simulate deletion
            progress_callback: Optional callback for progress updates
        
        Returns:
            Dictionary with results
        """
        df = self.queue_manager.load_queue("delete")
        
        if df.empty:
            logger.info("No blobs to delete")
            return {
                'success': True,
                'dry_run': dry_run,
                'deleted_count': 0,
                'failed_count': 0,
                'errors': [],
            }
        
        blob_names = df['name'].tolist()
        deleted = []
        failed = []
        errors = []
        
        iterator = tqdm(blob_names, desc="Deleting blobs") if not progress_callback else blob_names
        
        for i, blob_name in enumerate(iterator):
            try:
                if not dry_run:
                    blob_client = self.container_client.get_blob_client(blob_name)
                    blob_client.delete_blob()
                    
                    # Log audit event
                    self.queue_manager.log_audit_event(
                        blob_name=blob_name,
                        action="DELETED",
                        user="system",
                        reasoning="Executed from deletion queue",
                    )
                
                deleted.append(blob_name)
                
            except ResourceNotFoundError:
                logger.warning(f"Blob not found (already deleted?): {blob_name}")
                deleted.append(blob_name)
                
            except Exception as e:
                error_msg = f"Failed to delete {blob_name}: {str(e)}"
                logger.error(error_msg)
                failed.append(blob_name)
                errors.append(error_msg)
            
            if progress_callback:
                progress_callback(i + 1, len(blob_names))
        
        # Remove deleted blobs from queue
        if deleted:
            self.queue_manager.remove_from_queue("delete", deleted)
        
        result = {
            'success': len(failed) == 0,
            'dry_run': dry_run,
            'deleted_count': len(deleted),
            'failed_count': len(failed),
            'failed_blobs': failed,
            'errors': errors,
        }
        
        logger.info(f"Deletion complete: {len(deleted)} deleted, {len(failed)} failed (dry_run={dry_run})")
        return result


class AzureBlobCleanup:
    """Main orchestrator for Azure Blob Storage cleanup workflow."""
    
    def __init__(self, config: BlobCleanupConfig):
        # Validate config
        errors = config.validate()
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")
        
        self.config = config
        self.inventory = BlobInventory(config)
        self.llm_engine = LLMTriageEngine(config)
        self.queue_manager = QueueManager(config)
        self.deletion_manager = DeletionManager(config, self.queue_manager)
    
    def run_full_workflow(
        self,
        prefix: Optional[str] = None,
        skip_triage: bool = False
    ):
        """
        Run complete cleanup workflow:
        1. Create inventory manifest
        2. LLM-based triage
        3. Save to queues
        4. Return statistics
        """
        logger.info("Starting Azure Blob Cleanup workflow")
        
        # Step 1: Create manifest
        logger.info("Step 1: Creating blob inventory")
        manifest = self.inventory.create_manifest(prefix)
        
        if not manifest:
            logger.warning("No blobs found")
            return
        
        # Step 2: LLM triage
        if not skip_triage:
            logger.info("Step 2: Running LLM triage")
            decisions = self.llm_engine.batch_triage(manifest)
            
            # Step 3: Save to queues
            logger.info("Step 3: Saving triage decisions to queues")
            self.queue_manager.save_triage_decisions(manifest, decisions)
            
            # Statistics
            decision_counts = Counter(d.decision for d in decisions)
            logger.info(f"Triage complete: {dict(decision_counts)}")
        
        logger.info("Workflow complete")
    
    def create_review_ui(self) -> Optional[widgets.VBox]:
        """Create interactive review UI."""
        if not IPYWIDGETS_AVAILABLE:
            logger.error("ipywidgets not available")
            return None
        
        ui = ReviewUI(self.config, self.queue_manager, self.llm_engine)
        ui.load_review_queue()
        return ui.create_review_interface()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics across all queues."""
        stats = {}
        
        for queue_type in ["review", "delete", "keep"]:
            df = self.queue_manager.load_queue(queue_type)
            stats[queue_type] = {
                'count': len(df),
                'total_size_bytes': int(df['size'].sum()) if not df.empty else 0,
            }
        
        return stats


# Convenience functions for notebook usage
def create_cleanup_tool(
    config: Optional[BlobCleanupConfig] = None,
    env_file: Optional[str] = None
) -> AzureBlobCleanup:
    """
    Create and return an AzureBlobCleanup instance.
    
    Args:
        config: Optional BlobCleanupConfig. If not provided, loads from environment.
        env_file: Optional path to .env file
    
    Returns:
        AzureBlobCleanup instance
    """
    if config is None:
        config = BlobCleanupConfig.from_env(env_file)
    
    return AzureBlobCleanup(config)


def quick_start(env_file: Optional[str] = None) -> AzureBlobCleanup:
    """
    Quick start: Create cleanup tool and run full workflow.
    
    Args:
        env_file: Optional path to .env file
    
    Returns:
        AzureBlobCleanup instance with workflow complete
    """
    cleanup = create_cleanup_tool(env_file=env_file)
    cleanup.run_full_workflow()
    return cleanup
