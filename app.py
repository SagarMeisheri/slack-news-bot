"""
Streamlit Application: Real-Time News Intelligence & Scenario Analysis Console.
Built strictly on the Google Agent Development Kit (ADK) framework (google-adk, https://adk.dev/).
Features a Split-Screen Live Agent Workspace, Stage-by-Stage Real-Time Result Streaming,
ModelConfig with Thinking Levels, Saved Search History, and Direct Source-Linked Intelligence Briefs.
"""

import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_PYTHON_CONTEXT"] = "contextvars"

import asyncio
import time
from typing import Any, Dict, List, Optional
import streamlit as st
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

from agents import (
    BreakingFindings,
    CalendarFindings,
    PrecedentFindings,
    SynthesisOutput,
    build_adk_news_pipeline,
    format_report_markdown,
)
from config import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    ModelConfig,
    ThinkingMode,
    get_default_model_config,
)
from observability.tracker import ObservabilityTracker
from schemas.models import (
    BaselineBrief,
    IntelligenceReport,
    PipelineObservabilityReport,
    SafetyCheckResult,
    SearchStageResult,
    SpeculativeInquiry,
    SuppressionStatus,
)
from storage import (
    delete_saved_report,
    list_saved_reports,
    load_saved_report,
    save_report,
)
from tools.adk_tools import STAGE_DEFINITIONS
from tools.search_tool import consolidate_citations
from ui import (
    CUSTOM_CSS,
    render_agent_live_activity,
    render_citations,
    render_header,
    render_observability_drawer,
    render_onscreen_code_view,
    render_safety_notice,
    render_stage_explorer,
    render_stepper,
)

# Page Setup
st.set_page_config(
    page_title="Real-Time News Intelligence (ADK Console)",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Session State Initialization
if "report" not in st.session_state:
    st.session_state.report = None
if "agent_statuses" not in st.session_state:
    st.session_state.agent_statuses = {
        "safety": "pending",
        "breaking": "pending",
        "precedent": "pending",
        "calendar": "pending",
        "synthesis": "pending",
    }
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "active_observability" not in st.session_state:
    st.session_state.active_observability = None
if "active_state" not in st.session_state:
    st.session_state.active_state = {}


# Sidebar Configuration Controls
with st.sidebar:
    st.markdown("### ⚙️ ADK Multi-Agent Config")

    gemini_model = st.selectbox(
        "Gemini LLM Model",
        options=AVAILABLE_MODELS,
        index=0,
        help="Model powering the ADK LlmAgents in the SequentialAgent pipeline.",
    )

    thinking_level = st.selectbox(
        "Gemini Thinking Level",
        options=["minimal", "low", "medium", "high", "auto", "disabled"],
        index=0,
        help="Controls the reasoning depth and thought token budget for Gemini models.",
    )

    temperature = st.slider(
        "Sampling Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.2,
        step=0.05,
        help="Lower values yield more factual/grounded generation.",
    )

    search_mode = st.selectbox(
        "Parallel Search Mode",
        options=["fast", "turbo", "advanced"],
        index=0,
        help="Search mode preset for Parallel Search API.",
    )

    jurisdiction = st.selectbox(
        "Jurisdiction Legal Framework",
        options=["India (BNS / SEBI / Sub Judice)", "United States", "United Kingdom", "Global / Multi-Jurisdiction"],
        index=0,
        help="Primary jurisdiction for legal red-line checks and suppression protocols.",
    )
    jurisdiction_code = "India" if "India" in jurisdiction else jurisdiction.split()[0]

    st.divider()

    # Past Searches & History Manager
    st.markdown("### 📁 Saved Searches & History")
    saved_searches = list_saved_reports()

    if saved_searches:
        search_options = [
            f"{s['timestamp_str']} • {s['topic'][:35]}..."
            for s in saved_searches
        ]
        selected_search_idx = st.selectbox(
            "Select past investigation:",
            options=range(len(saved_searches)),
            format_func=lambda i: search_options[i],
            key="saved_search_selector",
        )

        col_load, col_del = st.columns([2, 1])
        with col_load:
            if st.button("📂 Load Search", use_container_width=True):
                target_report_meta = saved_searches[selected_search_idx]
                loaded_rep = load_saved_report(target_report_meta["id"])
                if loaded_rep:
                    st.session_state.report = loaded_rep
                    st.session_state.agent_statuses = {
                        "safety": "completed",
                        "breaking": "completed",
                        "precedent": "completed",
                        "calendar": "completed",
                        "synthesis": "completed",
                    }
                    st.session_state.active_observability = loaded_rep.observability_report
                    # Reconstruct active state for agent cards
                    st.session_state.active_state = {
                        "safety_result": loaded_rep.safety_result.model_dump(),
                        "stages_1_2": {"stage1_summary": loaded_rep.baseline_brief.core_event if loaded_rep.baseline_brief else "", "core_event_date": loaded_rep.baseline_brief.core_event_date if loaded_rep.baseline_brief else "", "stage2_summary": loaded_rep.baseline_brief.immediate_fallout if loaded_rep.baseline_brief else ""},
                        "stages_3_5": {"stage3_precedent_summary": loaded_rep.baseline_brief.context_precedent if loaded_rep.baseline_brief else ""},
                        "stages_6_7": {},
                        "synthesis_output": {"baseline_brief": loaded_rep.baseline_brief.model_dump() if loaded_rep.baseline_brief else {}, "inquiries": [inq.model_dump() for inq in loaded_rep.inquiries]},
                    }
                    st.success(f"Loaded: {target_report_meta['topic'][:30]}...")
                    st.rerun()
        with col_del:
            if st.button("🗑️ Delete", use_container_width=True):
                target_report_meta = saved_searches[selected_search_idx]
                delete_saved_report(target_report_meta["id"])
                st.info("Deleted.")
                st.rerun()
    else:
        st.caption("No past searches saved yet. Run a search to save results automatically.")

    st.divider()

    st.markdown("### 💡 Preset Investigation Topics")
    preset_topics = [
        "Select a preset or enter below...",
        "RBI draft guidelines on digital lending and NBFC capital adequacy norms",
        "SEBI disclosure framework on algorithmic trading and market maker incentives",
        "Supreme Court hearing on telecom adjusted gross revenue (AGR) dues",
        "India-Middle East-Europe Economic Corridor (IMEC) infrastructure rollout",
        "Government of India AI Mission compute infrastructure subsidy allocation",
    ]
    selected_preset = st.selectbox("Sample Topic", options=preset_topics, index=0)

    st.divider()

    # Framework & Key Badges
    st.markdown("### 🛠️ Framework & Keys")
    st.caption("Powered by **Google Agent Development Kit (ADK)**")
    gemini_key_present = bool(os.getenv("GEMINI_API_KEY"))
    parallel_key_present = bool(os.getenv("PARALLEL_API_KEY"))
    st.markdown(f"**Gemini API Key:** {'🟢 Active' if gemini_key_present else '🔴 Missing in .env'}")
    st.markdown(f"**Parallel Search Key:** {'🟢 Active' if parallel_key_present else '🔴 Missing in .env'}")


# Main Content Header
render_header()

# Query Input Container
with st.container():
    default_query_text = selected_preset if selected_preset != preset_topics[0] else ""
    user_query = st.text_input(
        "Enter breaking news statement, corporate event, or investigative query:",
        value=default_query_text,
        placeholder="e.g., RBI introduces new risk-weights on unsecured consumer credit",
    )

    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        run_btn = st.button("🚀 Run ADK Pipeline", type="primary", use_container_width=True)
    with col_info:
        st.caption("Executes ADK `SequentialAgent` across Safety Triage, 1-call budget search agents, and scenario synthesis with live stage-by-stage streaming.")


# Render Stepper Bar
stepper_placeholder = st.empty()
with stepper_placeholder.container():
    render_stepper(st.session_state.agent_statuses)


AGENT_MAP = {
    "Safety_Triage_Agent": "safety",
    "Breaking_Fallout_Investigator": "breaking",
    "Precedent_Counter_Investigator": "precedent",
    "Calendar_Filings_Investigator": "calendar",
    "Synthesis_Neutrality_Auditor": "synthesis",
}


# Split Screen Layout Placeholders
st.markdown("---")
col_agents_layout, col_output_layout = st.columns([1, 1], gap="large")

left_workspace_placeholder = col_agents_layout.empty()
right_output_placeholder = col_output_layout.empty()


def _render_left_workspace_view(statuses: Dict[str, str], obs_report: Optional[PipelineObservabilityReport], state: Dict[str, Any], stages: Optional[List[SearchStageResult]] = None):
    """Helper to render the left workspace view into a container."""
    with left_workspace_placeholder.container():
        render_agent_live_activity(
            agent_statuses=statuses,
            observability_report=obs_report,
            session_state=state,
            search_stages=stages,
        )
        if stages:
            st.markdown("")
            render_stage_explorer(stages)
        if obs_report and obs_report.total_duration_seconds > 0:
            st.markdown("")
            render_observability_drawer(obs_report, key_suffix="final_drawer")


def _render_right_output_view(report: Optional[IntelligenceReport], safety_result: Optional[SafetyCheckResult] = None, partial_markdown: Optional[str] = None):
    """Helper to render the right brief view into a container."""
    with right_output_placeholder.container():
        st.markdown("### 📋 Synthesized Intelligence Brief")

        if report:
            render_safety_notice(report.safety_result)
            st.markdown(
                f'<div class="report-card">{report.formatted_markdown}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")
            render_citations(report.citations_all)
            st.markdown("")
            render_onscreen_code_view(report)
        elif partial_markdown:
            if safety_result:
                render_safety_notice(safety_result)
            st.markdown(
                f'<div class="report-card">{partial_markdown}</div>',
                unsafe_allow_html=True,
            )
        elif safety_result:
            render_safety_notice(safety_result)
            st.info("⚡ Agents are investigating ground truth, precedent, and forward calendar...")
        else:
            st.info("👈 Enter a topic and click **🚀 Run ADK Pipeline** to view live multi-agent execution and the synthesized brief, or load a past search from the sidebar.")


async def run_adk_pipeline(
    topic: str,
    model_cfg: ModelConfig,
    jurisdiction_str: str,
    status_box,
):
    """
    Executes the ADK Sequential Pipeline with stage-by-stage live streaming updates to both UI columns.
    """
    statuses = {
        "safety": "pending",
        "breaking": "pending",
        "precedent": "pending",
        "calendar": "pending",
        "synthesis": "pending",
    }
    start_time = time.time()

    # Create Observability Tracker (with strict 1-call budget guardrail)
    tracker = ObservabilityTracker(
        topic=topic,
        pipeline_name="NewsIntelligencePipeline",
        max_tool_calls_per_agent=1,
    )

    # Build ADK SequentialAgent & InMemoryRunner with ModelConfig
    pipeline_agent, runner, _ = build_adk_news_pipeline(
        model_config=model_cfg,
        jurisdiction=jurisdiction_str,
        tracker=tracker,
    )
    user_id = "adk_streamlit_user"
    session = await runner.session_service.create_session(
        user_id=user_id,
        app_name=runner.app_name,
    )

    import datetime
    today_str = datetime.datetime.now().strftime("%B %d, %Y")
    current_year = datetime.datetime.now().strftime("%Y")

    user_msg = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text=(
                    f"Investigate the following breaking news topic adhering strictly to institutional master prompt "
                    f"search and scenario analysis protocols:\n"
                    f"Topic: \"{topic}\"\n"
                    f"Jurisdiction: {jurisdiction_str}\n"
                    f"Today's Date: {today_str} (Current Year: {current_year})\n"
                    f"Note: All temporal references ('0-7 days', 'past week', 'today', 'upcoming 90 days') must be anchored strictly to today's date ({today_str})."
                )
            )
        ],
    )

    current_agent_key = None
    last_known_state: Dict[str, Any] = {}

    # Stream ADK Events with live stage updates
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_msg,
    ):
        author = getattr(event, "author", None)
        if author and author in AGENT_MAP:
            new_key = AGENT_MAP[author]
            if new_key != current_agent_key:
                if current_agent_key:
                    statuses[current_agent_key] = "completed"
                current_agent_key = new_key
                statuses[current_agent_key] = "running"

        # Check for tool call events
        if event.content and event.content.parts:
            for p in event.content.parts:
                fn_call = getattr(p, "function_call", None)
                if fn_call:
                    tool_name = fn_call.name
                    status_box.info(f"⚡ **[{author}]** Invoking Search Tool: `{tool_name}` (Budget: 1 call)...")

        # Fetch current state to stream completed results immediately
        try:
            cur_session = await runner.session_service.get_session(
                user_id=user_id,
                session_id=session.id,
                app_name=runner.app_name,
            )
            if cur_session and cur_session.state:
                last_known_state = cur_session.state
        except Exception:
            pass

        # Update Stepper and Left Column Workspace
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_stepper(statuses)

        _render_left_workspace_view(statuses, tracker.report, last_known_state)

        # Update Right Column with partial findings as they arrive
        safety_dict = last_known_state.get("safety_result")
        safety_obj = SafetyCheckResult.model_validate(safety_dict) if safety_dict else None
        synth_dict = last_known_state.get("synthesis_output")
        partial_md = synth_dict.get("formatted_markdown") if synth_dict else None

        _render_right_output_view(None, safety_result=safety_obj, partial_markdown=partial_md)

    # Mark all completed
    for k in statuses:
        if statuses[k] == "running":
            statuses[k] = "completed"

    # Retrieve final ADK Session State
    final_session = await runner.session_service.get_session(
        user_id=user_id,
        session_id=session.id,
        app_name=runner.app_name,
    )
    state = final_session.state or last_known_state

    # Extract structured results
    raw_safety = state.get("safety_result", {})
    safety_res = SafetyCheckResult.model_validate(raw_safety) if raw_safety else SafetyCheckResult()

    if safety_res.status == SuppressionStatus.FULL_SUPPRESSION:
        statuses["safety"] = "suppressed"
    elif safety_res.status == SuppressionStatus.PARTIAL_SUPPRESSION:
        statuses["safety"] = "warning"

    raw_stages_1_2 = state.get("stages_1_2", {})
    raw_stages_3_5 = state.get("stages_3_5", {})
    raw_stages_6_7 = state.get("stages_6_7", {})
    raw_synthesis = state.get("synthesis_output", {})

    synthesis_res = SynthesisOutput.model_validate(raw_synthesis) if raw_synthesis else None

    # Reconstruct SearchStageResult list
    reconstructed_stages: List[SearchStageResult] = [
        SearchStageResult(
            stage_id=1,
            stage_name="Breaking Ground Truth",
            time_window="Strict: 0–7 days",
            objective=f"Primary event facts for '{topic}'",
            findings_summary=raw_stages_1_2.get("stage1_summary", "Ground truth investigated."),
            excerpts=[],
            citations=raw_stages_1_2.get("citations", []),
        ),
        SearchStageResult(
            stage_id=2,
            stage_name="Immediate Fallout & Stakeholders",
            time_window="Strict: 0–7 days",
            objective=f"Immediate market and sector reaction for '{topic}'",
            findings_summary=raw_stages_1_2.get("stage2_summary", "Fallout investigated."),
            excerpts=[],
            citations=raw_stages_1_2.get("citations", []),
        ),
        SearchStageResult(
            stage_id=3,
            stage_name="Precedent & Regulatory Context",
            time_window="All-time",
            objective=f"Statutory history and doctrines for '{topic}'",
            findings_summary=raw_stages_3_5.get("stage3_precedent_summary", "Precedents investigated."),
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=4,
            stage_name="Adversarial / Counter-Narrative",
            time_window="0–30 days",
            objective=f"Critics and counter-narratives for '{topic}'",
            findings_summary=raw_stages_3_5.get("stage4_counter_summary", "Counter-narratives investigated."),
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=5,
            stage_name="Analogous / Cross-Domain Precedent",
            time_window="All-time",
            objective=f"Analogous precedents and base rates for '{topic}'",
            findings_summary=f"{raw_stages_3_5.get('stage5_analogous_summary', '')}\nBase Rate: {raw_stages_3_5.get('base_rate_notes', '')}",
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=6,
            stage_name="Forward Calendar / Scheduled Events",
            time_window="Now–90 days",
            objective=f"Upcoming calendar milestone dates for '{topic}'",
            findings_summary=f"{raw_stages_6_7.get('stage6_calendar_summary', '')}\nUpcoming Dates: {', '.join(raw_stages_6_7.get('upcoming_dates', []))}",
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
        SearchStageResult(
            stage_id=7,
            stage_name="Primary Source / Site-Restricted",
            time_window="Conditional",
            objective=f"Direct official filings and gazettes for '{topic}'",
            findings_summary=raw_stages_6_7.get("stage7_primary_source_summary", "Primary filings investigated."),
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
    ]

    # Clean and enrich all citations across stages
    raw_citations_all = (
        raw_stages_1_2.get("citations", []) +
        raw_stages_3_5.get("citations", []) +
        raw_stages_6_7.get("citations", [])
    )
    all_citations = []
    seen_urls = set()
    for cit in raw_citations_all:
        if isinstance(cit, dict):
            u = cit.get("url", "").strip()
            if u and u not in seen_urls:
                seen_urls.add(u)
                sid = cit.get("stage_id")
                s_name = cit.get("stage_name")
                if sid:
                    try:
                        int_sid = int(sid)
                        if not s_name or s_name.strip() in ["Stage", "Stage Finding", "Stage "]:
                            s_name = STAGE_DEFINITIONS.get(int_sid, {}).get("name", f"Stage {int_sid}")
                    except (ValueError, TypeError):
                        pass
                cit["stage_name"] = s_name or "Verified Search Finding"
                all_citations.append(cit)

    # Use Gemini's direct markdown output if available, else fallback to formatted string
    if synthesis_res and synthesis_res.formatted_markdown and synthesis_res.formatted_markdown.strip():
        baseline_brief = synthesis_res.baseline_brief
        inquiries = synthesis_res.inquiries
        formatted_md = synthesis_res.formatted_markdown.strip()
    elif synthesis_res:
        baseline_brief = synthesis_res.baseline_brief
        inquiries = synthesis_res.inquiries
        formatted_md = format_report_markdown(
            baseline=baseline_brief,
            inquiries=inquiries,
            safety_notice=safety_res.safety_notice,
            is_full_suppression=(safety_res.status == SuppressionStatus.FULL_SUPPRESSION),
            citations=all_citations,
        )
    else:
        baseline_brief = BaselineBrief(
            core_event=raw_stages_1_2.get("stage1_summary", f"Developments regarding {topic}."),
            core_event_date=raw_stages_1_2.get("core_event_date", "Recent"),
            immediate_fallout=raw_stages_1_2.get("stage2_summary", "Market assessed."),
            context_precedent=raw_stages_3_5.get("stage3_precedent_summary", "Statutory framework applies."),
        )
        inquiries = []
        formatted_md = format_report_markdown(
            baseline=baseline_brief,
            inquiries=inquiries,
            safety_notice=safety_res.safety_notice,
            is_full_suppression=(safety_res.status == SuppressionStatus.FULL_SUPPRESSION),
            citations=all_citations,
        )

    exec_time = round(time.time() - start_time, 2)
    obs_report = tracker.finalize(is_successful=True)

    report = IntelligenceReport(
        query_topic=topic,
        jurisdiction=jurisdiction_str,
        safety_result=safety_res,
        search_stages=reconstructed_stages,
        baseline_brief=baseline_brief,
        inquiries=inquiries,
        citations_all=all_citations,
        formatted_markdown=formatted_md,
        execution_time_seconds=exec_time,
        observability_report=obs_report,
    )

    # Automatically save search report to disk
    save_report(report)

    # Final UI updates
    stepper_placeholder.empty()
    with stepper_placeholder.container():
        render_stepper(statuses)

    _render_left_workspace_view(statuses, obs_report, state, reconstructed_stages)
    _render_right_output_view(report)

    status_box.success(f"✨ **ADK Pipeline Completed & Saved** in {exec_time}s across all 5 ADK agents, thinking level '{model_cfg.thinking_level.value}', and full telemetry tracing!")
    return report, statuses, state


# Initial Render on page load
_render_left_workspace_view(
    st.session_state.agent_statuses,
    st.session_state.active_observability,
    st.session_state.active_state,
    st.session_state.report.search_stages if st.session_state.report else None,
)
_render_right_output_view(st.session_state.report)


# Trigger ADK Pipeline
if run_btn and user_query.strip():
    status_placeholder = st.empty()
    st.session_state.is_running = True

    model_config_obj = get_default_model_config(
        model_name=gemini_model,
        thinking_level=thinking_level,
        temperature=temperature,
    )

    try:
        report_data, final_statuses, final_state = asyncio.run(
            run_adk_pipeline(
                topic=user_query.strip(),
                model_cfg=model_config_obj,
                jurisdiction_str=jurisdiction_code,
                status_box=status_placeholder,
            )
        )
        st.session_state.report = report_data
        st.session_state.agent_statuses = final_statuses
        st.session_state.active_observability = report_data.observability_report
        st.session_state.active_state = final_state
    except Exception as e:
        st.error(f"❌ ADK Pipeline Execution Error: {e}")
    finally:
        st.session_state.is_running = False
