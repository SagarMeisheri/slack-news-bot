"""
Centralized Model and Generation Configuration Module.
Provides Pydantic-based configuration for Gemini models, thinking levels, and generation parameters.
"""

from enum import Enum
import os
from typing import List, Optional
from google.genai import types
from pydantic import BaseModel, Field


class ThinkingMode(str, Enum):
    DISABLED = "disabled"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTO = "auto"


# Supported Gemini Models per latest spec
AVAILABLE_MODELS: List[str] = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


class ModelConfig(BaseModel):
    """
    Pydantic Configuration for Model selection, generation parameters, and Thinking Levels.
    """
    model_name: str = Field(
        default=DEFAULT_MODEL,
        description="Target Gemini model name",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for generation",
    )
    thinking_level: ThinkingMode = Field(
        default=ThinkingMode.MINIMAL,
        description="Thinking level for reasoning models (disabled, minimal, low, medium, high, auto)",
    )
    thinking_budget: Optional[int] = Field(
        default=None,
        description="Explicit thinking token budget (0 = disabled, -1 = auto, >0 = token count)",
    )
    include_thoughts: bool = Field(
        default=True,
        description="Whether to include reasoning thoughts in the execution trace",
    )

    def to_generate_content_config(self) -> types.GenerateContentConfig:
        """
        Converts the Pydantic ModelConfig into a Google GenAI GenerateContentConfig.
        """
        # Determine thinking config parameters
        thinking_cfg = None

        if self.thinking_level == ThinkingMode.DISABLED:
            thinking_cfg = types.ThinkingConfig(
                thinking_budget=0,
                include_thoughts=False,
            )
        elif self.thinking_level == ThinkingMode.AUTO:
            thinking_cfg = types.ThinkingConfig(
                thinking_budget=-1,
                include_thoughts=self.include_thoughts,
            )
        else:
            level_map = {
                ThinkingMode.MINIMAL: types.ThinkingLevel.MINIMAL,
                ThinkingMode.LOW: types.ThinkingLevel.LOW,
                ThinkingMode.MEDIUM: types.ThinkingLevel.MEDIUM,
                ThinkingMode.HIGH: types.ThinkingLevel.HIGH,
            }
            mapped_level = level_map.get(self.thinking_level, types.ThinkingLevel.MINIMAL)
            budget = self.thinking_budget if self.thinking_budget is not None else None

            if budget is not None:
                thinking_cfg = types.ThinkingConfig(
                    thinking_budget=budget,
                    include_thoughts=self.include_thoughts,
                )
            else:
                try:
                    thinking_cfg = types.ThinkingConfig(
                        thinking_level=mapped_level,
                        include_thoughts=self.include_thoughts,
                    )
                except Exception:
                    thinking_cfg = types.ThinkingConfig(
                        thinking_budget=-1,
                        include_thoughts=self.include_thoughts,
                    )

        return types.GenerateContentConfig(
            temperature=self.temperature,
            thinking_config=thinking_cfg,
        )


def get_default_model_config(
    model_name: Optional[str] = None,
    thinking_level: str = "minimal",
    temperature: float = 0.2,
) -> ModelConfig:
    """
    Factory helper to create a ModelConfig instance.
    """
    selected_model = model_name or DEFAULT_MODEL
    try:
        th_mode = ThinkingMode(thinking_level.lower())
    except ValueError:
        th_mode = ThinkingMode.MINIMAL

    return ModelConfig(
        model_name=selected_model,
        temperature=temperature,
        thinking_level=th_mode,
    )
