"""
Prompts Package.
Provides centralized prompt management for all ADK agents.
"""

from prompts.loader import PromptMetadata, PromptRegistry, prompt_registry

__all__ = [
    "PromptMetadata",
    "PromptRegistry",
    "prompt_registry",
]
