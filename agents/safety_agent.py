"""
Agent 1: Safety & Suppression Triage Auditor using Google ADK.
Evaluates query topics against Universal and Jurisdiction-Specific Legal Red Lines
per master_prompt.md Section 1, 2, and 3.
"""

from typing import Optional
from config import ModelConfig, get_default_model_config
from google.adk.agents import LlmAgent
from observability.tracker import ObservabilityTracker
from prompts.loader import prompt_registry
from schemas.models import SafetyCheckResult


def create_safety_agent(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    jurisdiction: str = "India",
    name: str = "Safety_Triage_Agent",
    tracker: Optional[ObservabilityTracker] = None,
) -> LlmAgent:
    """Creates the ADK Safety & Suppression Triage Agent."""
    cfg = model_config or get_default_model_config(model_name=model)
    instruction = prompt_registry.get_safety_prompt(jurisdiction=jurisdiction)

    agent = LlmAgent(
        name=name,
        description="Audits topics for universal safety boundaries and jurisdiction legal red lines.",
        model=cfg.model_name,
        generate_content_config=cfg.to_generate_content_config(),
        instruction=instruction,
        output_schema=SafetyCheckResult,
        output_key="safety_result",
        before_agent_callback=tracker.on_before_agent if tracker else None,
        after_agent_callback=tracker.on_after_agent if tracker else None,
        before_model_callback=tracker.on_before_model if tracker else None,
        after_model_callback=tracker.on_after_model if tracker else None,
        before_tool_callback=tracker.on_before_tool if tracker else None,
        after_tool_callback=tracker.on_after_tool if tracker else None,
    )
    return agent
