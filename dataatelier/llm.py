"""LLM client abstraction for DataAtelier."""

import json
from abc import ABC, abstractmethod
from typing import Optional

from .models import FewShotExample


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    def call(self, prompt: str, temperature: float = 0.0) -> str:
        """Call the LLM with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Temperature for generation (0.0 = deterministic, higher = more random)
            
        Returns:
            The LLM's response as a string
            
        Raises:
            Exception: If the LLM call fails
        """
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI client implementation."""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        """Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key
            model: Model name (e.g., 'gpt-4', 'gpt-3.5-turbo')
        """
        import openai
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
    
    def call(self, prompt: str, temperature: float = 0.0) -> str:
        """Call OpenAI with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Temperature for generation
            
        Returns:
            The LLM's response as a string
            
        Raises:
            Exception: If the OpenAI API call fails
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content or ""


class AzureOpenAIClient(BaseLLMClient):
    """Azure OpenAI client implementation."""
    
    def __init__(self, endpoint: str, api_key: str, deployment: str):
        """Initialize Azure OpenAI client.
        
        Args:
            endpoint: Azure OpenAI endpoint URL
            api_key: Azure OpenAI API key
            deployment: Deployment name
        """
        import openai
        self.client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-02-01"
        )
        self.deployment = deployment
    
    def call(self, prompt: str, temperature: float = 0.0) -> str:
        """Call Azure OpenAI with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Temperature for generation
            
        Returns:
            The LLM's response as a string
            
        Raises:
            Exception: If the Azure OpenAI API call fails
        """
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content or ""


class OllamaClient(BaseLLMClient):
    """Ollama client implementation."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2"):
        """Initialize Ollama client.
        
        Args:
            base_url: Ollama server base URL
            model: Model name
        """
        import openai
        self.client = openai.OpenAI(
            base_url=f"{base_url}/v1",
            api_key="ollama"  # Ollama doesn't require a real API key
        )
        self.model = model
    
    def call(self, prompt: str, temperature: float = 0.0) -> str:
        """Call Ollama with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Temperature for generation
            
        Returns:
            The LLM's response as a string
            
        Raises:
            Exception: If the Ollama API call fails
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content or ""


def create_llm_client(config) -> BaseLLMClient:
    """Factory function to create an LLM client based on config.
    
    Args:
        config: Config object with LLM provider settings
        
    Returns:
        BaseLLMClient instance (OpenAIClient, AzureOpenAIClient, or OllamaClient)
        
    Raises:
        ValueError: If provider is invalid or required settings are missing
    """
    provider = config.llm_provider.lower()
    
    if provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OpenAI API key is required")
        return OpenAIClient(
            api_key=config.openai_api_key,
            model=config.openai_model
        )
    
    elif provider == "azure_openai":
        if not config.azure_openai_endpoint:
            raise ValueError("Azure OpenAI endpoint is required")
        if not config.azure_openai_api_key:
            raise ValueError("Azure OpenAI API key is required")
        if not config.azure_openai_deployment:
            raise ValueError("Azure OpenAI deployment is required")
        return AzureOpenAIClient(
            endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            deployment=config.azure_openai_deployment
        )
    
    elif provider == "ollama":
        return OllamaClient(
            base_url=config.ollama_base_url,
            model=config.ollama_model
        )
    
    else:
        raise ValueError(f"Invalid LLM provider: {provider}. Must be 'openai', 'azure_openai', or 'ollama'")


def build_triage_prompt(
    metadata: dict,
    preview: str,
    policy: str,
    examples: list[FewShotExample]
) -> str:
    """Build a triage prompt for the LLM.
    
    Args:
        metadata: Dictionary with blob metadata (name, path, size, last_modified, content_type, etc.)
        preview: Preview of the blob content
        policy: Policy document text
        examples: List of few-shot examples
        
    Returns:
        Formatted prompt string for the LLM
    """
    # Format examples
    examples_text = ""
    if examples:
        examples_text = "\n## Few-Shot Examples\n\n"
        for i, ex in enumerate(examples, 1):
            examples_text += f"### Example {i}\n"
            examples_text += f"**Label:** {ex.label}\n"
            examples_text += f"**Reason:** {ex.reason}\n"
            examples_text += f"**Path Hint:** {ex.path_hint}\n"
            examples_text += f"**Content Type:** {ex.content_type}\n"
            examples_text += f"**Date:** {ex.date}\n"
            examples_text += f"**Excerpt:**\n```\n{ex.excerpt}\n```\n\n"
    
    # Format metadata
    metadata_text = "## Blob Metadata\n\n"
    metadata_text += f"- **Name:** {metadata.get('name', 'unknown')}\n"
    metadata_text += f"- **Path:** {metadata.get('path', 'unknown')}\n"
    metadata_text += f"- **Size:** {metadata.get('size', 0)} bytes\n"
    metadata_text += f"- **Content Type:** {metadata.get('content_type', 'unknown')}\n"
    metadata_text += f"- **Last Modified:** {metadata.get('last_modified', 'unknown')}\n"
    
    # Format preview
    preview_text = "## Content Preview\n\n"
    if preview:
        preview_text += f"```\n{preview}\n```\n"
    else:
        preview_text += "(No preview available)\n"
    
    # Build full prompt
    prompt = f"""You are an AI assistant helping to triage Azure Blob Storage files for cleanup. Your job is to determine whether a blob should be kept, deleted, or sent for human review.

# Policy

{policy}

{examples_text}
{metadata_text}
{preview_text}

# Your Task

Based on the policy, examples, metadata, and content preview above, make a decision about this blob.

You MUST respond with a JSON object in this exact format:
{{
    "label": "keep" | "delete" | "human_review",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation of your decision"
}}

Remember:
- Be CONSERVATIVE: When in doubt, choose "human_review"
- Only use "delete" or "keep" if you are highly confident (≥0.95)
- Check NEVER DELETE constraints first
- Provide clear, specific reasoning
- Your response must be valid JSON
"""
    
    return prompt


def parse_llm_response(response_text: str) -> dict:
    """Parse LLM response into a structured dictionary.
    
    Args:
        response_text: Raw response text from the LLM
        
    Returns:
        Dictionary with keys: 'label', 'confidence', 'reason'
        
    Raises:
        ValueError: If response cannot be parsed or is missing required fields
    """
    try:
        # Try to parse as JSON
        data = json.loads(response_text.strip())
        
        # Validate required fields
        if 'label' not in data:
            raise ValueError("Missing 'label' field in LLM response")
        if 'confidence' not in data:
            raise ValueError("Missing 'confidence' field in LLM response")
        if 'reason' not in data:
            raise ValueError("Missing 'reason' field in LLM response")
        
        # Validate label
        label = data['label'].lower()
        if label not in ('keep', 'delete', 'human_review'):
            raise ValueError(f"Invalid label: {label}. Must be 'keep', 'delete', or 'human_review'")
        
        # Validate confidence
        confidence = float(data['confidence'])
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError(f"Invalid confidence: {confidence}. Must be between 0.0 and 1.0")
        
        return {
            'label': label,
            'confidence': confidence,
            'reason': str(data['reason'])
        }
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}") from e
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Invalid LLM response format: {e}") from e
