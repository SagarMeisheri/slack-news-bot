"""
ADK Observability Tracker Module.
Implements Google Agent Development Kit (ADK) callback handlers to monitor,
trace, and profile agents, tools, and model interactions in real time,
and enforces runtime constraints (such as the strict 1-search-call budget per agent).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from google.adk.agents.context import Context
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from schemas.models import (
    AgentExecutionTrace,
    ModelCallTrace,
    PipelineObservabilityReport,
    ToolCallTrace,
)

logger = logging.getLogger(__name__)

INTERNAL_ADK_TOOLS = {
    "set_model_response",
    "transfer_to_parent",
    "transfer_to_agent",
    "exit_loop",
    "load_artifacts",
    "save_artifact",
}


class ObservabilityTracker:
    """
    Centralized ADK Callback Observer and Guardrail Controller that captures
    execution traces, latencies, state transitions, and enforces search tool budgets.
    """

    def __init__(
        self,
        topic: str = "",
        pipeline_name: str = "NewsIntelligencePipeline",
        max_tool_calls_per_agent: int = 1,
    ):
        self.max_tool_calls_per_agent = max_tool_calls_per_agent
        self.report = PipelineObservabilityReport(
            pipeline_name=pipeline_name,
            topic=topic,
            start_time=time.time(),
        )
        self._active_tools: Dict[str, ToolCallTrace] = {}
        self._active_models: Dict[str, ModelCallTrace] = {}
        self._agent_tool_counts: Dict[str, int] = {}

    def reset(self, topic: str = "", pipeline_name: str = "NewsIntelligencePipeline") -> None:
        """Resets tracker state for a new pipeline execution."""
        self.report = PipelineObservabilityReport(
            pipeline_name=pipeline_name,
            topic=topic,
            start_time=time.time(),
        )
        self._active_tools.clear()
        self._active_models.clear()
        self._agent_tool_counts.clear()

    # -----------------------------------------------------------------
    # Agent Lifecycle Callbacks
    # -----------------------------------------------------------------

    def on_before_agent(
        self,
        callback_context: Optional[Context] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[types.Content]:
        """Triggered immediately before an ADK agent starts executing."""
        ctx = callback_context or (p_args[0] if p_args else None) or kwargs.get("context")
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"
        logger.info(f"[ADK Observability] ▶ Starting Agent: {agent_name}")

        trace = self.report.agent_traces.get(agent_name)
        if not trace:
            trace = AgentExecutionTrace(
                agent_name=agent_name,
                status="running",
                start_time=time.time(),
            )
            self.report.agent_traces[agent_name] = trace
        else:
            trace.status = "running"
            trace.start_time = time.time()

        return None

    def on_after_agent(
        self,
        callback_context: Optional[Context] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[types.Content]:
        """Triggered immediately after an ADK agent completes execution."""
        ctx = callback_context or (p_args[0] if p_args else None) or kwargs.get("context")
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"
        logger.info(f"[ADK Observability] ⏹ Completed Agent: {agent_name}")

        trace = self.report.agent_traces.get(agent_name)
        if trace:
            trace.end_time = time.time()
            if trace.start_time:
                trace.duration_seconds = round(trace.end_time - trace.start_time, 3)
            trace.status = "completed"

            # Check if agent produced output in state
            state = getattr(ctx, "state", None)
            if state:
                for key in ["safety_result", "stages_1_2", "stages_3_5", "stages_6_7", "synthesis_output"]:
                    if key in state:
                        trace.output_key = key
                        val = state[key]
                        if isinstance(val, dict):
                            trace.output_summary = f"Keys: {list(val.keys())}"
                        elif hasattr(val, "model_dump"):
                            trace.output_summary = f"Keys: {list(val.model_dump().keys())}"

        return None

    # -----------------------------------------------------------------
    # Model Callbacks
    # -----------------------------------------------------------------

    def on_before_model(
        self,
        callback_context: Optional[Context] = None,
        llm_request: Optional[LlmRequest] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[LlmResponse]:
        """Triggered before sending a request to the LLM."""
        ctx = callback_context or (p_args[0] if p_args else None) or kwargs.get("context")
        req = llm_request or (p_args[1] if len(p_args) > 1 else None) or kwargs.get("request")
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"
        prompt_snippet = ""
        if req and req.contents:
            last_content = req.contents[-1]
            if last_content.parts:
                for p in last_content.parts:
                    if hasattr(p, "text") and p.text:
                        prompt_snippet = p.text[:300]
                        break

        model_trace = ModelCallTrace(
            agent_name=agent_name,
            model=getattr(req, "model", "gemini-3.1-flash-lite") or "gemini-3.1-flash-lite",
            prompt_preview=prompt_snippet,
            start_time=time.time(),
        )
        self._active_models[agent_name] = model_trace
        return None

    def on_after_model(
        self,
        callback_context: Optional[Context] = None,
        llm_response: Optional[LlmResponse] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[LlmResponse]:
        """Triggered upon receiving a response from the LLM."""
        ctx = callback_context or (p_args[0] if p_args else None) or kwargs.get("context")
        resp = llm_response or (p_args[1] if len(p_args) > 1 else None) or kwargs.get("response")
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"
        model_trace = self._active_models.pop(agent_name, None)
        if model_trace:
            model_trace.end_time = time.time()
            model_trace.duration_ms = round((model_trace.end_time - model_trace.start_time) * 1000, 2)

            resp_snippet = ""
            thought_snippet = ""
            if resp and resp.content and resp.content.parts:
                for p in resp.content.parts:
                    is_thought = getattr(p, "thought", False) is True
                    p_text = getattr(p, "text", "") or ""
                    if is_thought:
                        if p_text:
                            thought_snippet += (p_text + "\n")
                    else:
                        if p_text and not resp_snippet:
                            resp_snippet = p_text[:400]

            thought_snippet = thought_snippet.strip()
            if thought_snippet:
                model_trace.thinking_trace = thought_snippet
                logger.info(f"[ADK Thinking Trace] 💭 [{agent_name}] Thought Process: {thought_snippet[:200]}...")

            model_trace.response_preview = resp_snippet

            trace = self.report.agent_traces.get(agent_name)
            if trace:
                trace.model_calls.append(model_trace)
                if thought_snippet and thought_snippet not in trace.thinking_traces:
                    trace.thinking_traces.append(thought_snippet)
            self.report.total_model_calls += 1

        return None

    def record_thought(self, agent_name: str, thought_text: str) -> None:
        """Records a real-time streamed thought chunk for an agent."""
        if not thought_text or not thought_text.strip():
            return
        clean = thought_text.strip()
        trace = self.report.agent_traces.get(agent_name)
        if not trace:
            trace = AgentExecutionTrace(agent_name=agent_name, status="running", start_time=time.time())
            self.report.agent_traces[agent_name] = trace

        if clean not in trace.thinking_traces:
            trace.thinking_traces.append(clean)
        logger.info(f"[ADK Live Thought] 💭 [{agent_name}]: {clean[:150]}...")

    # -----------------------------------------------------------------
    # Tool Callbacks & Constraint Guardrail
    # -----------------------------------------------------------------

    def on_before_tool(
        self,
        tool: BaseTool,
        args: Dict[str, Any],
        tool_context: Optional[ToolContext] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Triggered before executing an ADK FunctionTool.
        Enforces search tool budgets while preserving internal tools (e.g. set_model_response).
        """
        ctx = tool_context or kwargs.get("callback_context") or (p_args[0] if p_args else None)
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"
        tool_name = getattr(tool, "name", "") or ""

        # NEVER block internal ADK tools
        if tool_name in INTERNAL_ADK_TOOLS or not tool_name.startswith("search_stage_"):
            return None

        current_count = self._agent_tool_counts.get(agent_name, 0)

        # Enforce search budget guardrail
        if current_count >= self.max_tool_calls_per_agent:
            logger.warning(
                f"[ADK Guardrail] 🛑 Agent '{agent_name}' exceeded search tool budget "
                f"(max {self.max_tool_calls_per_agent}). Blocking tool '{tool_name}'."
            )
            return {
                "status": "blocked",
                "reason": (
                    f"Search tool budget exceeded: Each agent is strictly permitted a maximum of "
                    f"{self.max_tool_calls_per_agent} search call. "
                    f"Please synthesize findings immediately with existing results using set_model_response."
                ),
            }

        self._agent_tool_counts[agent_name] = current_count + 1
        logger.info(f"[ADK Observability] ⚡ Invoking Search Tool: `{tool_name}` for Agent: `{agent_name}` (Call #{current_count + 1}) with args: {args}")

        call_key = f"{agent_name}:{tool_name}:{time.time()}"
        tool_trace = ToolCallTrace(
            tool_name=tool_name,
            agent_name=agent_name,
            arguments=args,
            start_time=time.time(),
        )
        self._active_tools[call_key] = tool_trace
        return None

    def on_after_tool(
        self,
        tool: BaseTool,
        args: Dict[str, Any],
        tool_context: Optional[ToolContext] = None,
        tool_response: Optional[Dict[str, Any]] = None,
        *p_args: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Triggered after executing an ADK FunctionTool.
        """
        ctx = tool_context or kwargs.get("callback_context") or (p_args[0] if p_args else None)
        resp = tool_response or kwargs.get("response") or (p_args[1] if len(p_args) > 1 else None)
        tool_name = getattr(tool, "name", "") or ""
        agent_name = getattr(ctx, "agent_name", None) or "UnknownAgent"

        if tool_name in INTERNAL_ADK_TOOLS or not tool_name.startswith("search_stage_"):
            return None

        # Find matching active tool trace
        matching_key = None
        for key in reversed(list(self._active_tools.keys())):
            if key.startswith(f"{agent_name}:{tool_name}"):
                matching_key = key
                break

        tool_trace = self._active_tools.pop(matching_key, None) if matching_key else None
        if not tool_trace:
            tool_trace = ToolCallTrace(
                tool_name=tool_name,
                agent_name=agent_name,
                arguments=args,
                start_time=time.time() - 0.1,
            )

        tool_trace.end_time = time.time()
        tool_trace.duration_ms = round((tool_trace.end_time - tool_trace.start_time) * 1000, 2)
        tool_trace.raw_result = resp

        # Generate excerpt summary
        if isinstance(resp, str):
            tool_trace.result_summary = resp[:200]
        elif isinstance(resp, dict):
            keys = list(resp.keys())
            tool_trace.result_summary = f"Dict with keys: {keys}"
        else:
            tool_trace.result_summary = str(resp)[:200]

        trace = self.report.agent_traces.get(agent_name)
        if trace:
            trace.tool_calls.append(tool_trace)
        self.report.total_tool_calls += 1

        return None

    def finalize(self, is_successful: bool = True, error_message: Optional[str] = None) -> PipelineObservabilityReport:
        """Finalizes and returns the complete pipeline observability report."""
        self.report.end_time = time.time()
        self.report.total_duration_seconds = round(self.report.end_time - self.report.start_time, 2)
        self.report.is_successful = is_successful
        self.report.error_message = error_message
        return self.report
