"""
Agent 2: Breaking Ground Truth & Immediate Fallout Investigator using Google ADK.
Executes Stage 1 (0-7 days Breaking Ground Truth) and Stage 2 (0-7 days Immediate Fallout & Stakeholders)
using ADK FunctionTools and parallel search, synthesizing facts, dates, and sector reactions.
"""

from typing import List, Optional
from config import ModelConfig, get_default_model_config
from google.adk.agents import LlmAgent
from agents.guardrails import enforce_tool_call_budget
from observability.tracker import ObservabilityTracker
from prompts.loader import prompt_registry
from schemas.models import BreakingFindings
from tools.adk_tools import BREAKING_TOOLS


def create_breaking_agent(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    name: str = "Breaking_Fallout_Investigator",
    tracker: Optional[ObservabilityTracker] = None,
    max_tool_calls: int = 1,
) -> LlmAgent:
    """Creates the ADK Breaking Ground Truth & Immediate Fallout Agent with hardcoded tool budget and model config."""
    cfg = model_config or get_default_model_config(model_name=model)
    instruction = prompt_registry.get_breaking_prompt()

    before_tool_callbacks = [enforce_tool_call_budget(max_calls=max_tool_calls)]
    if tracker:
        before_tool_callbacks.append(tracker.on_before_tool)

    return LlmAgent(
        name=name,
        description="Executes Stage 1 (Ground Truth 0-7d) and Stage 2 (Immediate Fallout 0-7d) searches via Parallel Search tools.",
        model=cfg.model_name,
        generate_content_config=cfg.to_generate_content_config(),
        instruction=instruction,
        tools=BREAKING_TOOLS,
        output_schema=BreakingFindings,
        output_key="stages_1_2",
        before_agent_callback=tracker.on_before_agent if tracker else None,
        after_agent_callback=tracker.on_after_agent if tracker else None,
        before_model_callback=tracker.on_before_model if tracker else None,
        after_model_callback=tracker.on_after_model if tracker else None,
        before_tool_callback=before_tool_callbacks,
        after_tool_callback=tracker.on_after_tool if tracker else None,
    )
