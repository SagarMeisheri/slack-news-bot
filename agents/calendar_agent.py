"""
Agent 4: Forward Calendar & Primary Source Investigator using Google ADK.
Executes Stage 6 (Now-90 days Forward Calendar) and Stage 7 (Official Primary Sources / Gazette / Circulars)
using ADK FunctionTools and parallel search.
"""

from typing import List, Optional
from config import ModelConfig, get_default_model_config
from google.adk.agents import LlmAgent
from agents.guardrails import enforce_tool_call_budget
from observability.tracker import ObservabilityTracker
from prompts.loader import prompt_registry
from schemas.models import CalendarFindings
from tools.adk_tools import CALENDAR_TOOLS


def create_calendar_agent(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    name: str = "Calendar_Filings_Investigator",
    tracker: Optional[ObservabilityTracker] = None,
    max_tool_calls: int = 1,
) -> LlmAgent:
    """Creates the ADK Forward Calendar & Primary Sources Agent with hardcoded tool budget and model config."""
    cfg = model_config or get_default_model_config(model_name=model)
    instruction = prompt_registry.get_calendar_prompt()

    before_tool_callbacks = [enforce_tool_call_budget(max_calls=max_tool_calls)]
    if tracker:
        before_tool_callbacks.append(tracker.on_before_tool)

    return LlmAgent(
        name=name,
        description="Executes Stage 6 (Forward Calendar) and Stage 7 (Primary Source Filings) searches via Parallel Search tools.",
        model=cfg.model_name,
        generate_content_config=cfg.to_generate_content_config(),
        instruction=instruction,
        tools=CALENDAR_TOOLS,
        output_schema=CalendarFindings,
        output_key="stages_6_7",
        before_agent_callback=tracker.on_before_agent if tracker else None,
        after_agent_callback=tracker.on_after_agent if tracker else None,
        before_model_callback=tracker.on_before_model if tracker else None,
        after_model_callback=tracker.on_after_model if tracker else None,
        before_tool_callback=before_tool_callbacks,
        after_tool_callback=tracker.on_after_tool if tracker else None,
    )
