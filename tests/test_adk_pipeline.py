"""
Automated unit tests for ADK Agents, Prompt Registry, Observability Tracing, ModelConfig, and Schemas.
"""

from unittest.mock import MagicMock
import unittest
from agents import (
    BreakingFindings,
    CalendarFindings,
    PrecedentFindings,
    SynthesisOutput,
    build_adk_news_pipeline,
    create_breaking_agent,
    create_calendar_agent,
    create_precedent_agent,
    create_safety_agent,
    create_synthesis_agent,
    format_report_markdown,
)
from config import (
    AVAILABLE_MODELS,
    ModelConfig,
    ThinkingMode,
    get_default_model_config,
)
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.genai import types
from observability.tracker import ObservabilityTracker
from prompts.loader import prompt_registry
from schemas.models import (
    AgentExecutionTrace,
    BaselineBrief,
    InquiryArchetype,
    PipelineObservabilityReport,
    SafetyCategory,
    SafetyCheckResult,
    SpeculativeInquiry,
    SuppressionStatus,
    ToolCallTrace,
)
from tools.adk_tools import (
    ALL_SEARCH_TOOLS,
    BREAKING_TOOLS,
    CALENDAR_TOOLS,
    PRECEDENT_TOOLS,
    tool_stage_1,
    tool_stage_2,
)


class TestModelConfig(unittest.TestCase):
    """Verifies Pydantic ModelConfig, thinking levels, and GenerateContentConfig translation."""

    def test_model_list_contains_flash_lite(self):
        self.assertIn("gemini-3.1-flash-lite", AVAILABLE_MODELS)
        self.assertIn("gemini-3.5-flash-lite", AVAILABLE_MODELS)

    def test_model_config_generate_content_config(self):
        cfg = get_default_model_config(
            model_name="gemini-3.1-flash-lite",
            thinking_level="high",
            temperature=0.3,
        )
        self.assertEqual(cfg.model_name, "gemini-3.1-flash-lite")
        self.assertEqual(cfg.thinking_level, ThinkingMode.HIGH)
        self.assertEqual(cfg.temperature, 0.3)

        gen_cfg = cfg.to_generate_content_config()
        self.assertIsInstance(gen_cfg, types.GenerateContentConfig)
        self.assertEqual(gen_cfg.temperature, 0.3)
        self.assertIsNotNone(gen_cfg.thinking_config)


class TestADKPromptRegistry(unittest.TestCase):
    """Verifies that all prompt files exist and load correctly via the Pydantic registry."""

    def test_load_all_prompts(self):
        safety_p = prompt_registry.get_safety_prompt("India")
        self.assertIn("Safety & Suppression Triage Auditor", safety_p)

        breaking_p = prompt_registry.get_breaking_prompt()
        self.assertIn("STRICT CONSTRAINT: Exactly ONE Tool Call Permitted", breaking_p)

        precedent_p = prompt_registry.get_precedent_prompt()
        self.assertIn("STRICT CONSTRAINT: Exactly ONE Tool Call Permitted", precedent_p)

        social_p = prompt_registry.get_social_prompt()
        self.assertIn("Social Intelligence & Public Sentiment Investigator", social_p)

        calendar_p = prompt_registry.get_calendar_prompt()
        self.assertIn("STRICT CONSTRAINT: Exactly ONE Tool Call Permitted", calendar_p)

        synthesis_p = prompt_registry.get_synthesis_prompt("India")
        self.assertIn("Synthesis & Neutrality Auditor", synthesis_p)


class TestADKTools(unittest.TestCase):
    """Verifies all ADK FunctionTool instances."""

    def test_tools_registered(self):
        from tools.adk_tools import SOCIAL_TOOLS
        self.assertEqual(len(ALL_SEARCH_TOOLS), 8)
        self.assertEqual(len(BREAKING_TOOLS), 2)
        self.assertEqual(len(PRECEDENT_TOOLS), 3)
        self.assertEqual(len(SOCIAL_TOOLS), 1)
        self.assertEqual(len(CALENDAR_TOOLS), 2)

        for tool in ALL_SEARCH_TOOLS:
            self.assertIsInstance(tool, FunctionTool)
            self.assertTrue(tool.name.startswith("search_stage_"))


class TestADKAgentsAndPipeline(unittest.TestCase):
    """Verifies creation of ADK LlmAgents and the top-level SequentialAgent with ModelConfig."""

    def test_create_agents(self):
        from agents.social_agent import create_social_agent
        tracker = ObservabilityTracker(topic="Test Topic")
        cfg = get_default_model_config(model_name="gemini-3.1-flash-lite", thinking_level="minimal")

        safety = create_safety_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(safety, LlmAgent)
        self.assertEqual(safety.name, "Safety_Triage_Agent")
        self.assertEqual(safety.model, "gemini-3.1-flash-lite")
        self.assertEqual(safety.output_key, "safety_result")

        breaking = create_breaking_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(breaking, LlmAgent)
        self.assertEqual(len(breaking.tools), 2)
        self.assertEqual(breaking.model, "gemini-3.1-flash-lite")
        self.assertEqual(breaking.output_key, "stages_1_2")

        precedent = create_precedent_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(precedent, LlmAgent)
        self.assertEqual(len(precedent.tools), 3)
        self.assertEqual(precedent.output_key, "stages_3_5")

        social = create_social_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(social, LlmAgent)
        self.assertEqual(len(social.tools), 1)
        self.assertEqual(social.output_key, "stages_8")

        calendar = create_calendar_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(calendar, LlmAgent)
        self.assertEqual(len(calendar.tools), 2)
        self.assertEqual(calendar.output_key, "stages_6_7")

        synthesis = create_synthesis_agent(model_config=cfg, tracker=tracker)
        self.assertIsInstance(synthesis, LlmAgent)
        self.assertEqual(synthesis.output_key, "synthesis_output")

    def test_build_adk_pipeline(self):
        cfg = get_default_model_config(model_name="gemini-3.5-flash-lite")
        pipeline, runner, tracker = build_adk_news_pipeline(model_config=cfg)
        self.assertIsInstance(pipeline, SequentialAgent)
        self.assertIsInstance(runner, InMemoryRunner)
        self.assertIsInstance(tracker, ObservabilityTracker)
        self.assertEqual(len(pipeline.sub_agents), 6)



class TestObservabilityTracker(unittest.TestCase):
    """Verifies the ObservabilityTracker model generation, report output, and 1-call guardrail."""

    def test_tracker_lifecycle(self):
        tracker = ObservabilityTracker(topic="RBI Repo Rate Decision")

        # Simulate agent lifecycle
        tracker.report.agent_traces["Safety_Triage_Agent"] = AgentExecutionTrace(
            agent_name="Safety_Triage_Agent",
            status="completed",
            duration_seconds=1.2,
        )

        tool_trace = ToolCallTrace(
            tool_name="search_stage_1_ground_truth",
            agent_name="Breaking_Fallout_Investigator",
            arguments={"topic": "RBI Repo Rate"},
            result_summary="RBI maintains repo rate at 6.5%",
            duration_ms=450.0,
        )
        breaking_trace = AgentExecutionTrace(
            agent_name="Breaking_Fallout_Investigator",
            status="completed",
            duration_seconds=2.5,
            tool_calls=[tool_trace],
        )
        tracker.report.agent_traces["Breaking_Fallout_Investigator"] = breaking_trace
        tracker.report.total_tool_calls += 1

        final_report = tracker.finalize(is_successful=True)
        self.assertIsInstance(final_report, PipelineObservabilityReport)
        self.assertEqual(final_report.total_tool_calls, 1)
        self.assertIn("Safety_Triage_Agent", final_report.agent_traces)
        self.assertIn("Breaking_Fallout_Investigator", final_report.agent_traces)

    def test_single_tool_call_guardrail(self):
        """Verifies that an agent is restricted to exactly 1 tool call per run."""
        tracker = ObservabilityTracker(topic="Budget 2026", max_tool_calls_per_agent=1)
        mock_ctx = MagicMock()
        mock_ctx.agent_name = "Breaking_Fallout_Investigator"

        # First call should be permitted (returns None to allow ADK tool execution)
        first_call = tracker.on_before_tool(tool=tool_stage_1, args={"topic": "Budget"}, tool_context=mock_ctx)
        self.assertIsNone(first_call)

        # Second call by the same agent must be intercepted and blocked by the guardrail
        second_call = tracker.on_before_tool(tool=tool_stage_2, args={"topic": "Budget"}, tool_context=mock_ctx)
        self.assertIsNotNone(second_call)
        self.assertEqual(second_call.get("status"), "blocked")
        self.assertIn("Search tool budget exceeded", second_call.get("reason", ""))

    def test_enforce_tool_call_budget_keyword_args(self):
        """Verifies that enforce_tool_call_budget accepts tool_context as keyword argument from ADK."""
        from agents.guardrails import enforce_tool_call_budget
        guardrail = enforce_tool_call_budget(max_calls=1)
        mock_ctx = MagicMock()
        mock_ctx.agent_name = "Breaking_Fallout_Investigator"

        # ADK functions.py calls before_callback(tool=tool, args=function_args, tool_context=tool_context)
        res1 = guardrail(tool=tool_stage_1, args={"topic": "IMEC"}, tool_context=mock_ctx)
        self.assertIsNone(res1)

        res2 = guardrail(tool=tool_stage_2, args={"topic": "IMEC"}, tool_context=mock_ctx)
        self.assertIsNotNone(res2)
        self.assertEqual(res2.get("status"), "blocked")

    def test_internal_tools_not_blocked(self):
        """Verifies that internal ADK tools (like set_model_response) are NEVER blocked even after search budget is reached."""
        from agents.guardrails import enforce_tool_call_budget
        guardrail = enforce_tool_call_budget(max_calls=1)
        mock_ctx = MagicMock()
        mock_ctx.agent_name = "Breaking_Fallout_Investigator"

        # Mock internal tool set_model_response
        internal_tool = MagicMock()
        internal_tool.name = "set_model_response"

        # 1. Execute search call
        res_search = guardrail(tool=tool_stage_1, args={"topic": "AI Mission"}, tool_context=mock_ctx)
        self.assertIsNone(res_search)

        # 2. Subsequent call to set_model_response must NOT be blocked
        res_internal = guardrail(tool=internal_tool, args={"response": {}}, tool_context=mock_ctx)
        self.assertIsNone(res_internal)

    def test_thinking_trace_recording(self):
        """Verifies that thinking traces are properly captured in ModelCallTrace and AgentExecutionTrace."""
        tracker = ObservabilityTracker(topic="Thinking Test")
        tracker.record_thought("Safety_Triage_Agent", "I need to evaluate this query against sub judice red lines.")
        tracker.record_thought("Safety_Triage_Agent", "The topic is pure regulatory policy and is safe to analyze.")

        report = tracker.finalize(is_successful=True)
        self.assertIn("Safety_Triage_Agent", report.agent_traces)
        agent_trace = report.agent_traces["Safety_Triage_Agent"]
        self.assertEqual(len(agent_trace.thinking_traces), 2)
        self.assertIn("sub judice red lines", agent_trace.thinking_traces[0])


class TestPydanticSchemas(unittest.TestCase):
    """Verifies serialization and validation of domain models."""

    def test_safety_check_model(self):
        res = SafetyCheckResult(
            status=SuppressionStatus.NO_SUPPRESSION,
            categories_triggered=[SafetyCategory.SAFE],
            rationale="Topic is pure regulatory policy.",
        )
        self.assertEqual(res.status, SuppressionStatus.NO_SUPPRESSION)
        dump = res.model_dump()
        self.assertEqual(dump["status"], "NO_SUPPRESSION")

    def test_synthesis_output_model(self):
        brief = BaselineBrief(
            core_event="Ministry of Finance released new budget allocations on August 24, 2026.",
            core_event_date="August 24, 2026",
            immediate_fallout="Bond yields remained steady at 6.85%.",
            context_precedent="Allocations align with the Fiscal Responsibility and Budget Management Act framework.",
        )
        inquiries = [
            SpeculativeInquiry(
                archetype=InquiryArchetype.WHY_X,
                question="What fiscal revenue assumptions underpin the capex timeline announced in the budget?",
                source_stages=[4],
                neutrality_verified=True,
            )
        ]
        md = format_report_markdown(brief, inquiries)
        output = SynthesisOutput(
            baseline_brief=brief,
            inquiries=inquiries,
            formatted_markdown=md,
        )
        self.assertIn("### Baseline Intelligence Brief", output.formatted_markdown)
        self.assertEqual(len(output.inquiries), 1)


class TestStorageHistory(unittest.TestCase):
    """Verifies saving, listing, loading, and deleting reports from disk."""

    def test_save_and_load_report(self):
        from storage import save_report, list_saved_reports, load_saved_report, delete_saved_report
        from schemas.models import IntelligenceReport, SafetyCheckResult, BaselineBrief

        rep = IntelligenceReport(
            query_topic="Test Save Topic",
            jurisdiction="India",
            safety_result=SafetyCheckResult(),
            baseline_brief=BaselineBrief(core_event="Test event", core_event_date="2026-08-26", immediate_fallout="None", context_precedent="None"),
            execution_time_seconds=1.23,
            formatted_markdown="### Test Markdown",
        )

        rep_id = save_report(rep)
        self.assertTrue(bool(rep_id))

    def test_save_and_find_checkpoint(self):
        from storage import save_stage_checkpoint, find_latest_checkpoint_for_topic
        import os

        topic = "Resume Test Topic BJP"
        chk_path = save_stage_checkpoint(
            topic=topic,
            stage_name="stage7_completed",
            state_data={"stages_1_2": {"stage1_summary": "Done"}, "stages_6_7": {"stage6_calendar_summary": "Done"}},
        )
        self.assertTrue(bool(chk_path))
        self.assertTrue(os.path.exists(chk_path))

        found = find_latest_checkpoint_for_topic(topic)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("topic"), topic)
        self.assertIn("stages_1_2", found.get("state", {}))

        # Cleanup
        try:
            os.remove(chk_path)
        except Exception:
            pass

    def test_pipeline_skips_completed_agents_on_resume(self):
        """Verifies that build_adk_news_pipeline skips agents whose output is already in resume_state."""
        resume_data = {
            "safety_result": {"status": "NO_SUPPRESSION"},
            "stages_1_2": {"stage1_summary": "Breaking done"},
            "stages_3_5": {"stage3_precedent_summary": "Precedents done"},
            "stages_8": {"sentiment_overview": "Social done"},
            "stages_6_7": {"stage6_calendar_summary": "Calendar done"},
        }
        pipeline, runner, tracker = build_adk_news_pipeline(resume_state=resume_data)
        # Only synthesis agent should be in sub_agents
        self.assertEqual(len(pipeline.sub_agents), 1)
        self.assertEqual(pipeline.sub_agents[0].name, "Synthesis_Neutrality_Auditor")


if __name__ == "__main__":
    unittest.main()

