"""
ADK Agent Guardrails Module.
Provides hardcoded callback guardrails for agent initialization per Google ADK best practices.
Enforces search tool budgets while preserving internal ADK framework tools (e.g., set_model_response).
"""

import logging
from typing import Any, Callable, Dict, Optional
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)

# List of internal ADK framework tools that should NEVER be counted towards the user search budget
INTERNAL_ADK_TOOLS = {
    "set_model_response",
    "transfer_to_parent",
    "transfer_to_agent",
    "exit_loop",
    "load_artifacts",
    "save_artifact",
}


def enforce_tool_call_budget(max_calls: int = 1) -> Callable[..., Optional[Dict[str, Any]]]:
    """
    Creates a hardcoded ADK `before_tool_callback` guardrail enforcing a strict search tool call budget.
    Excludes internal ADK tools (such as `set_model_response`) to allow structured output generation.

    Args:
        max_calls: Maximum number of search tool calls permitted for the agent (default: 1).

    Returns:
        ADK-compliant before_tool_callback function.
    """
    search_call_counts: Dict[str, int] = {}

    def _guardrail(
        tool: BaseTool,
        args: Dict[str, Any],
        tool_context: Optional[ToolContext] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        tool_name = getattr(tool, "name", "") or ""

        # NEVER block internal ADK framework tools (e.g. set_model_response for structured output)
        if tool_name in INTERNAL_ADK_TOOLS or not tool_name.startswith("search_stage_"):
            return None

        # Resolve context
        ctx = tool_context or kwargs.get("callback_context") or (p_args[0] if p_args else None)
        agent_name = getattr(ctx, "agent_name", None) or "Agent"
        current_count = search_call_counts.get(agent_name, 0)

        if current_count >= max_calls:
            logger.warning(
                f"[ADK Guardrail] 🛑 Agent '{agent_name}' exceeded search tool budget "
                f"(max {max_calls}). Intercepted additional search tool '{tool_name}'."
            )
            return {
                "status": "blocked",
                "reason": (
                    f"Search tool budget reached: You have already executed your allowed {max_calls} search call. "
                    f"Do not invoke further search tools. Please synthesize your findings and call set_model_response."
                ),
            }

        search_call_counts[agent_name] = current_count + 1
        logger.info(f"[ADK Guardrail] ✅ Permitted search #{current_count + 1} ('{tool_name}') for Agent '{agent_name}'.")
        return None

    return _guardrail
