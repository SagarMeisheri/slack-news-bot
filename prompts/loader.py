"""
Prompt Registry and Loader Module.
Provides Pydantic-validated loading, caching, and dynamic variable formatting for agent prompts,
including real-time temporal anchoring with today's date.
"""

import datetime
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field


PROMPTS_DIR = Path(__file__).parent.resolve()


def get_current_date_str() -> str:
    """Returns today's date formatted as 'Month DD, YYYY' (e.g., 'August 26, 2026')."""
    return datetime.datetime.now().strftime("%B %d, %Y")


def get_current_year_str() -> str:
    """Returns current year as a string (e.g., '2026')."""
    return datetime.datetime.now().strftime("%Y")


class PromptMetadata(BaseModel):
    name: str = Field(..., description="Prompt identifier name")
    file_path: str = Field(..., description="Path to the markdown prompt file")
    description: str = Field(..., description="Role and objective description")


class PromptRegistry(BaseModel):
    """
    Registry that manages loading, caching, and formatting of markdown prompts with temporal anchors.
    """
    cached_prompts: Dict[str, str] = Field(default_factory=dict)

    def load(self, prompt_name: str, variables: Optional[Dict[str, str]] = None) -> str:
        """
        Loads prompt content by name from the prompts directory, caches it, and applies dynamic formatting.
        """
        if prompt_name not in self.cached_prompts:
            file_name = f"{prompt_name}.md" if not prompt_name.endswith(".md") else prompt_name
            target_path = PROMPTS_DIR / file_name
            if not target_path.exists():
                raise FileNotFoundError(f"Prompt file not found at '{target_path}'")
            content = target_path.read_text(encoding="utf-8").strip()
            self.cached_prompts[prompt_name] = content

        text = self.cached_prompts[prompt_name]

        # Populate default temporal variables if not explicitly provided
        all_vars = {
            "today_date": get_current_date_str(),
            "current_year": get_current_year_str(),
        }
        if variables:
            all_vars.update(variables)

        for key, val in all_vars.items():
            text = text.replace(f"{{{{{key}}}}}", str(val))
        return text

    def get_safety_prompt(self, jurisdiction: str = "India", today_date: Optional[str] = None) -> str:
        vars_dict = {"jurisdiction": jurisdiction}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("safety_agent", vars_dict)

    def get_breaking_prompt(self, today_date: Optional[str] = None) -> str:
        vars_dict = {}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("breaking_agent", vars_dict)

    def get_precedent_prompt(self, today_date: Optional[str] = None) -> str:
        vars_dict = {}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("precedent_agent", vars_dict)

    def get_calendar_prompt(self, today_date: Optional[str] = None) -> str:
        vars_dict = {}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("calendar_agent", vars_dict)

    def get_social_prompt(self, today_date: Optional[str] = None) -> str:
        vars_dict = {}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("social_agent", vars_dict)

    def get_synthesis_prompt(self, jurisdiction: str = "India", today_date: Optional[str] = None) -> str:
        vars_dict = {"jurisdiction": jurisdiction}
        if today_date:
            vars_dict["today_date"] = today_date
        return self.load("synthesis_agent", vars_dict)


# Global default instance
prompt_registry = PromptRegistry()

