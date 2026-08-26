"""
Agents Package.
Exports specialized ADK agents, pipeline constructors, synthesis helpers, and guardrails.
"""

from agents.breaking_agent import create_breaking_agent
from agents.calendar_agent import create_calendar_agent
from agents.guardrails import enforce_tool_call_budget
from agents.pipeline import build_adk_news_pipeline
from agents.precedent_agent import create_precedent_agent
from agents.safety_agent import create_safety_agent
from agents.synthesis_agent import create_synthesis_agent, format_report_markdown
from schemas.models import (
    BreakingFindings,
    CalendarFindings,
    PrecedentFindings,
    SynthesisOutput,
)

__all__ = [
    "create_safety_agent",
    "create_breaking_agent",
    "create_precedent_agent",
    "create_calendar_agent",
    "create_synthesis_agent",
    "build_adk_news_pipeline",
    "format_report_markdown",
    "enforce_tool_call_budget",
    "BreakingFindings",
    "PrecedentFindings",
    "CalendarFindings",
    "SynthesisOutput",
]
