"""
Model Configuration - LLM model settings
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_MODEL = "MiniMax-M2.7"
DEFAULT_API_URL = "https://api.minimaxi.com/anthropic/v1/messages"
DEFAULT_PROVIDER = "minimax"


@dataclass
class ModelConfig:
    """Model configuration for LLM."""
    model: str = DEFAULT_MODEL
    api_url: str = DEFAULT_API_URL
    api_key: str = ""
    provider: str = DEFAULT_PROVIDER
    temperature: float = 0.1
    max_tokens: int = 150000
    timeout: int = 180


def get_model_config() -> ModelConfig:
    """
    Get model configuration from environment or defaults.

    Returns:
        ModelConfig instance
    """
    return ModelConfig(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        api_url=os.environ.get("CLAUDE_API_URL", DEFAULT_API_URL),
        api_key=os.environ.get("CLAUDE_API_KEY", ""),
        provider=os.environ.get("CLAUDE_PROVIDER", DEFAULT_PROVIDER),
        temperature=float(os.environ.get("CLAUDE_TEMPERATURE", "0.1")),
        max_tokens=int(os.environ.get("CLAUDE_MAX_TOKENS", "150000")),
        timeout=int(os.environ.get("CLAUDE_TIMEOUT", "180")),
    )


def validate_model_config(config: ModelConfig) -> tuple[bool, Optional[str]]:
    """
    Validate model configuration.

    Args:
        config: Model configuration to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not config.model:
        return False, "Model name is required"

    if not config.api_url:
        return False, "API URL is required"

    if not config.api_key:
        return False, "API key is required"

    if config.temperature < 0 or config.temperature > 1:
        return False, "Temperature must be between 0 and 1"

    if config.timeout <= 0:
        return False, "Timeout must be positive"

    return True, None


def get_supported_models() -> list[str]:
    """
    Get list of supported models.

    Returns:
        List of supported model names
    """
    return [
        "MiniMax-M2.7",
        "MiniMax-M2",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ]
