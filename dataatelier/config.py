"""Configuration management for DataAtelier."""

import os
from typing import Optional


class Config:
    """Configuration for Azure Blob Storage cleanup.
    
    Loads settings from environment variables or constructor parameters.
    """
    
    def __init__(
        self,
        storage_connection_string: Optional[str] = None,
        container_name: Optional[str] = None,
        llm_provider: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openai_model: Optional[str] = None,
        azure_openai_endpoint: Optional[str] = None,
        azure_openai_api_key: Optional[str] = None,
        azure_openai_deployment: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        max_files: int = -1,
        preview_size_kb: int = 4,
        confidence_threshold: float = 0.95,
        self_consistency_runs: int = 3,
        batch_size: int = 20,
    ):
        """Initialize configuration.
        
        Args:
            storage_connection_string: Azure Storage connection string
            container_name: Container name to clean
            llm_provider: LLM provider (openai, azure_openai, ollama)
            openai_api_key: OpenAI API key
            openai_model: OpenAI model name
            azure_openai_endpoint: Azure OpenAI endpoint
            azure_openai_api_key: Azure OpenAI API key
            azure_openai_deployment: Azure OpenAI deployment name
            ollama_base_url: Ollama base URL
            ollama_model: Ollama model name
            max_files: Maximum files to process (-1 for all)
            preview_size_kb: Preview size in KB
            confidence_threshold: Minimum confidence for auto-labeling
            self_consistency_runs: Number of LLM runs for self-consistency
            batch_size: Batch size for processing
        """
        # Azure Storage
        self.storage_connection_string = storage_connection_string or os.getenv(
            'AZURE_STORAGE_CONNECTION_STRING'
        )
        self.container_name = container_name or os.getenv('AZURE_STORAGE_CONTAINER_NAME')
        
        # LLM Provider
        self.llm_provider = llm_provider or os.getenv('LLM_PROVIDER', 'openai')
        
        # OpenAI
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.openai_model = openai_model or os.getenv('OPENAI_MODEL', 'gpt-4')
        
        # Azure OpenAI
        self.azure_openai_endpoint = azure_openai_endpoint or os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_openai_api_key = azure_openai_api_key or os.getenv('AZURE_OPENAI_API_KEY')
        self.azure_openai_deployment = azure_openai_deployment or os.getenv(
            'AZURE_OPENAI_DEPLOYMENT'
        )
        
        # Ollama
        self.ollama_base_url = ollama_base_url or os.getenv(
            'OLLAMA_BASE_URL', 'http://localhost:11434'
        )
        self.ollama_model = ollama_model or os.getenv('OLLAMA_MODEL', 'llama2')
        
        # Processing settings
        self.max_files = max_files if max_files != -1 else int(os.getenv('MAX_FILES', '-1'))
        self.preview_size_kb = preview_size_kb
        self.confidence_threshold = confidence_threshold
        self.self_consistency_runs = self_consistency_runs
        self.batch_size = batch_size
        
        # File paths
        self.manifest_file = 'manifest.csv'
        self.to_review_file = 'to_review.csv'
        self.to_delete_file = 'to_delete.csv'
        self.to_keep_file = 'to_keep.csv'
        self.policy_file = 'llm_policy.md'
        self.few_shot_file = 'few_shot_examples.jsonl'
        self.predictions_file = 'llm_predictions.parquet'
        self.audit_log_file = 'audit_log.csv'
    
    def validate(self) -> list[str]:
        """Validate configuration.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not self.storage_connection_string:
            errors.append("Missing AZURE_STORAGE_CONNECTION_STRING")
        
        if not self.container_name:
            errors.append("Missing AZURE_STORAGE_CONTAINER_NAME")
        
        if self.llm_provider == 'openai' and not self.openai_api_key:
            errors.append("Missing OPENAI_API_KEY for OpenAI provider")
        
        if self.llm_provider == 'azure_openai':
            if not self.azure_openai_endpoint:
                errors.append("Missing AZURE_OPENAI_ENDPOINT")
            if not self.azure_openai_api_key:
                errors.append("Missing AZURE_OPENAI_API_KEY")
            if not self.azure_openai_deployment:
                errors.append("Missing AZURE_OPENAI_DEPLOYMENT")
        
        if self.confidence_threshold < 0 or self.confidence_threshold > 1:
            errors.append("Confidence threshold must be between 0 and 1")
        
        if self.self_consistency_runs < 1:
            errors.append("Self-consistency runs must be >= 1")
        
        return errors
