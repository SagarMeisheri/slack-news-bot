"""
UI Components for the Streamlit News Intelligence Console.
Renders the split-screen Multi-Agent Workspace (with live streaming LLM results, Gemini thinking traces,
and Parallel Search API payloads), Final Brief with clickable links, On-Screen LLM Output Viewer, and Stepper badges.
"""

import json
from typing import Any, Dict, List, Optional
import streamlit as st
from schemas.models import (
    IntelligenceReport,
    PipelineObservabilityReport,
    SafetyCheckResult,
    SearchStageResult,
    SuppressionStatus,
    ToolCallTrace,
)


def render_header():
    st.markdown(
        """
        <div class="main-header">
            <h1>🌐 Real-Time News Intelligence & Scenario Analysis</h1>
            <p>Autonomous 5-agent ADK pipeline with live telemetry, single-search budget constraint per agent, Gemini thinking traces, and source-grounded scenario synthesis.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(agent_statuses: Dict[str, str]):
    """
    Renders dynamic visual status cards for the 5 agents.
    """
    agents = [
        ("safety", "1. Safety Triage", "Legal red lines & suppression"),
        ("breaking", "2. Ground Truth", "Stage 1 or 2 (0-7d window)"),
        ("precedent", "3. Precedent", "Stage 3, 4, or 5 context"),
        ("calendar", "4. Calendar", "Stage 6 or 7 milestones"),
        ("synthesis", "5. Synthesis", "Brief & 8 Archetypes"),
    ]

    cols = st.columns(5)
    icons = {
        "pending": "⏳",
        "running": "⚡",
        "completed": "✅",
        "warning": "⚠️",
        "suppressed": "🛑",
        "error": "❌",
    }

    for col, (key, title, subtitle) in zip(cols, agents):
        status = agent_statuses.get(key, "pending")
        icon = icons.get(status, "⏳")
        with col:
            st.markdown(
                f"""
                <div class="step-card {status}">
                    <div><span>{icon}</span> <strong>{title}</strong></div>
                    <div style="font-size: 0.72rem; opacity: 0.85;">{subtitle}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_safety_notice(safety: SafetyCheckResult):
    """
    Renders safety and suppression notices.
    """
    if safety.status == SuppressionStatus.FULL_SUPPRESSION:
        st.error(
            f"🛑 **FULL SUPPRESSION ACTIVE**\n\n"
            f"{safety.safety_notice or 'Speculative scenario generation suppressed due to legal or sub judice constraints.'}\n\n"
            f"**Rationale:** {safety.rationale}"
        )
    elif safety.status == SuppressionStatus.PARTIAL_SUPPRESSION:
        st.warning(
            f"⚠️ **PARTIAL SUPPRESSION ACTIVE**\n\n"
            f"{safety.safety_notice}\n\n"
            f"**Suppressed Elements:** {', '.join(safety.suppressed_elements) if safety.suppressed_elements else 'Sensitive sub-topics'}\n\n"
            f"**Permitted Safe Elements:** {', '.join(safety.safe_elements) if safety.safe_elements else 'Core operational facts'}"
        )
    else:
        st.success("✅ **Safety Clearance:** Topic cleared against Universal and Jurisdiction Legal Red Lines.")


def render_citations(citations: List[Dict]):
    """
    Renders citation links in an expandable drawer or list.
    """
    if not citations:
        st.info("No external URL citations retrieved.")
        return

    st.markdown("#### 🔗 Grounding Sources & Citations")
    chips = []
    for cit in citations:
        title = cit.get("title", "Source Link")
        url = cit.get("url", "#")
        stage = cit.get("stage_name", "")
        pub = f" ({cit.get('publish_date')})" if cit.get("publish_date") else ""
        chips.append(
            f'<a href="{url}" target="_blank" class="citation-chip" title="{stage}{pub}">📎 {title[:55]}...</a>'
        )
    st.markdown("".join(chips), unsafe_allow_html=True)


def _render_parallel_tool_result(tc: ToolCallTrace):
    """
    Renders the exact Parallel Search API return payload, including executed queries,
    extracted excerpts, and returned citations.
    """
    raw = tc.raw_result
    parsed = None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
    elif isinstance(raw, dict):
        parsed = raw

    if parsed and isinstance(parsed, dict):
        obj = parsed.get("objective")
        queries = parsed.get("queries_executed", [])
        excerpts = parsed.get("verified_excerpts", [])
        citations = parsed.get("citations", [])

        st.markdown(f"**🌐 Parallel Search API Output (`{tc.tool_name}`):**")
        if obj:
            st.caption(f"🎯 **Target Objective:** {obj}")
        if queries:
            st.caption(f"🔎 **Queries Executed:** `{', '.join(queries)}`")

        col1, col2 = st.columns(2)
        with col1:
            if excerpts:
                with st.popover(f"📄 View {len(excerpts)} Verified Excerpts from Search API"):
                    for idx, exc in enumerate(excerpts, 1):
                        st.markdown(f"**[{idx}]** > {exc}")
        with col2:
            if citations:
                with st.popover(f"🔗 View {len(citations)} Retrieved Source Citations"):
                    for cit in citations:
                        t = cit.get("title", "Source")
                        u = cit.get("url", "#")
                        d = f" ({cit.get('publish_date')})" if cit.get("publish_date") else ""
                        st.markdown(f"- [{t}]({u}){d}")

        with st.popover("📦 View Full Raw Parallel API JSON Payload"):
            st.json(parsed, expanded=False)
    elif raw:
        with st.popover(f"📦 View Tool Result ({tc.tool_name})"):
            if isinstance(raw, (dict, list)):
                st.json(raw, expanded=False)
            else:
                st.code(str(raw), language="json")


def render_agent_live_activity(
    agent_statuses: Dict[str, str],
    observability_report: Optional[PipelineObservabilityReport],
    session_state: Optional[Dict[str, Any]] = None,
    search_stages: Optional[List[SearchStageResult]] = None,
):
    """
    Renders what each agent did in real-time, including:
    - Active status & duration
    - Selected search tool & arguments
    - Exact Parallel Search API return payload (queries, excerpts, links)
    - Gemini thinking traces & reasoning thought tokens
    - LLM-generated results, findings summaries, dates, and metrics
    - Model call previews
    """
    st.markdown("### 🤖 Live Agent Execution Workspace")

    agent_meta = [
        ("Safety_Triage_Agent", "safety", "🛡️ Agent 1: Safety & Suppression Auditor", "safety_result", "Audits query against legal red lines (sub judice, rumors, emergency)."),
        ("Breaking_Fallout_Investigator", "breaking", "⚡ Agent 2: Breaking Ground Truth & Fallout", "stages_1_2", "Evaluates context and executes 1 search call (Stage 1 or Stage 2)."),
        ("Precedent_Counter_Investigator", "precedent", "📚 Agent 3: Precedent & Counter-Narrative", "stages_3_5", "Evaluates context and executes 1 search call (Stage 3, 4, or 5)."),
        ("Calendar_Filings_Investigator", "calendar", "📅 Agent 4: Forward Calendar & Primary Sources", "stages_6_7", "Evaluates context and executes 1 search call (Stage 6 or Stage 7)."),
        ("Synthesis_Neutrality_Auditor", "synthesis", "⚖️ Agent 5: Synthesis & Neutrality Auditor", "synthesis_output", "Synthesizes Baseline Brief and 10-20 Inquiries with clickable source links."),
    ]

    traces = observability_report.agent_traces if observability_report else {}
    state = session_state or {}

    for agent_id, status_key, display_name, state_key, description in agent_meta:
        status = agent_statuses.get(status_key, "pending")
        trace = traces.get(agent_id)
        duration_str = f" • {trace.duration_seconds}s" if trace and trace.duration_seconds else ""
        agent_data = state.get(state_key, {})

        is_expanded = status in ["running", "completed", "warning", "suppressed"]

        with st.expander(f"{display_name} [{status.upper()}]{duration_str}", expanded=is_expanded):
            st.caption(description)

            # 1. Show Tool Call Details & Parallel API Response
            if trace and trace.tool_calls:
                st.markdown("**⚡ Tool Executed (1-Call Budget):**")
                for tc in trace.tool_calls:
                    st.markdown(f"- Tool: `{tc.tool_name}` (`{tc.duration_ms} ms`)")
                    if tc.arguments:
                        st.json(tc.arguments, expanded=False)
                    
                    # Render Parallel Search API results for this tool call
                    _render_parallel_tool_result(tc)

            # 2. Show Gemini Thinking Process & Reasoning Traces
            agent_thoughts = getattr(trace, "thinking_traces", None) if trace else None
            if trace and agent_thoughts:
                st.markdown("---")
                st.markdown("💭 **Gemini Thinking Traces & Reasoning:**")
                for idx, thought_block in enumerate(agent_thoughts, 1):
                    with st.popover(f"🧠 View Thinking Trace #{idx} ({len(thought_block.split())} words)"):
                        st.markdown(thought_block)

            # 3. Show LLM Results & Generated Findings
            if agent_data:
                st.markdown("---")
                st.markdown("**🧠 LLM Output & Findings:**")

                # Agent 1: Safety Results
                if state_key == "safety_result":
                    s_status = agent_data.get("status", "NO_SUPPRESSION")
                    s_rat = agent_data.get("rationale", "")
                    s_cats = agent_data.get("categories_triggered", [])
                    st.markdown(f"- **Safety Status:** `{s_status}`")
                    if s_cats:
                        st.markdown(f"- **Categories:** `{', '.join(s_cats)}`")
                    if s_rat:
                        st.markdown(f"- **Rationale:** {s_rat}")
                    if agent_data.get("safety_notice"):
                        st.warning(agent_data.get("safety_notice"))

                # Agent 2: Breaking Ground Truth & Fallout
                elif state_key == "stages_1_2":
                    date_val = agent_data.get("core_event_date")
                    if date_val:
                        st.markdown(f"- 📅 **Core Event Date:** `{date_val}`")
                    s1 = agent_data.get("stage1_summary")
                    if s1:
                        st.markdown(f"- 📌 **Stage 1 (Ground Truth):** {s1}")
                    s2 = agent_data.get("stage2_summary")
                    if s2:
                        st.markdown(f"- 💥 **Stage 2 (Immediate Fallout):** {s2}")
                    metrics = agent_data.get("key_metrics", [])
                    if metrics:
                        st.markdown(f"- 📊 **Key Metrics:** {', '.join(metrics)}")
                    conflicts = agent_data.get("source_conflicts", [])
                    if conflicts:
                        st.markdown(f"- ⚠️ **Source Discrepancies:** {', '.join(conflicts)}")

                # Agent 3: Precedent & Counter-Narratives
                elif state_key == "stages_3_5":
                    s3 = agent_data.get("stage3_precedent_summary")
                    if s3:
                        st.markdown(f"- 📜 **Stage 3 (Precedent & History):** {s3}")
                    s4 = agent_data.get("stage4_counter_summary")
                    if s4:
                        st.markdown(f"- 🗣️ **Stage 4 (Counter-Narrative & Critics):** {s4}")
                    s5 = agent_data.get("stage5_analogous_summary")
                    if s5:
                        st.markdown(f"- 🔄 **Stage 5 (Analogous Precedents):** {s5}")
                    br = agent_data.get("base_rate_notes")
                    if br:
                        st.markdown(f"- 📈 **Base Rate Analysis:** {br}")

                # Agent 4: Forward Calendar & Primary Sources
                elif state_key == "stages_6_7":
                    dates = agent_data.get("upcoming_dates", [])
                    if dates:
                        st.markdown("**📅 Upcoming Milestone Dates:**")
                        for d in dates:
                            st.markdown(f"  - 🗓️ {d}")
                    s6 = agent_data.get("stage6_calendar_summary")
                    if s6:
                        st.markdown(f"- ⏳ **Stage 6 (Calendar Summary):** {s6}")
                    s7 = agent_data.get("stage7_primary_source_summary")
                    if s7:
                        st.markdown(f"- 🏛️ **Stage 7 (Primary Filings):** {s7}")

                # Agent 5: Synthesis Output
                elif state_key == "synthesis_output":
                    brief = agent_data.get("baseline_brief", {})
                    inqs = agent_data.get("inquiries", [])
                    st.markdown(f"- ✅ **Baseline Brief Synthesized:** Core event dated `{brief.get('core_event_date', 'Recent')}`")
                    st.markdown(f"- 🎯 **Grounded Inquiries Generated:** `{len(inqs)}` standalone questions across 8 archetypes")
                    st.caption("Rendered markdown report displayed in the right panel.")

            # 4. Model LLM Invocations preview
            if trace and trace.model_calls:
                st.caption(f"🤖 LLM Calls: {len(trace.model_calls)} invocation(s)")
                for mc in trace.model_calls:
                    btn_label = f"View Model Invocations ({mc.model} • {mc.duration_ms}ms)"
                    with st.popover(btn_label):
                        mc_thought = getattr(mc, "thinking_trace", None)
                        if mc_thought:
                            st.markdown("💭 **Reasoning Thoughts:**")
                            st.info(mc_thought)
                        if mc.response_preview:
                            st.markdown("📄 **Output Preview:**")
                            st.code(mc.response_preview, language="json")

            # Fallback status text
            if not trace and not agent_data:
                if status == "running":
                    st.info("⚡ Agent is executing contextual investigation...")
                elif status == "pending":
                    st.caption("⏳ Waiting for preceding pipeline stage...")
                else:
                    st.caption(f"Status: {status}")


def render_stage_explorer(stages: List[SearchStageResult]):
    """
    Renders an interactive accordion of search stages with Parallel API results.
    """
    with st.expander("🔍 7-Stage Search & Evidential Findings Explorer", expanded=False):
        for st_res in stages:
            st.markdown(f"#### Stage {st_res.stage_id}: {st_res.stage_name} (`{st_res.time_window}`)")
            st.markdown(f"**Objective:** {st_res.objective}")
            st.markdown(f"**Queries Executed:** `{', '.join(st_res.queries_executed)}`")
            st.markdown(f"**Summary:**\n{st_res.findings_summary}")

            if st_res.excerpts:
                with st.popover(f"View {len(st_res.excerpts)} Raw Excerpts for Stage {st_res.stage_id}"):
                    for exc in st_res.excerpts:
                        st.markdown(f"> {exc}")

            if st_res.citations:
                with st.popover(f"View {len(st_res.citations)} Stage {st_res.stage_id} Citations"):
                    for cit in st_res.citations:
                        t = cit.get("title", "Source")
                        u = cit.get("url", "#")
                        st.markdown(f"- [{t}]({u})")

            if st_res.evidence_note:
                st.caption(f"ℹ️ Evidence Note: {st_res.evidence_note}")
            st.divider()


def render_observability_drawer(report: Optional[PipelineObservabilityReport], key_suffix: str = "obs", **kwargs: Any):
    """
    Renders telemetry overview and on-screen trace data.
    """
    if not report:
        return

    with st.expander("📊 ADK Pipeline Telemetry & Trace Inspector", expanded=False):
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Execution Duration", f"{report.total_duration_seconds}s")
        with m2:
            st.metric("Total Tool Calls", report.total_tool_calls)
        with m3:
            st.metric("Total Model Calls", report.total_model_calls)
        with m4:
            st.metric("Pipeline Health", "🟢 Normal" if report.is_successful else "🔴 Error")

        st.markdown("**Structured Observability Trace:**")
        st.json(report.model_dump(), expanded=False)


def render_onscreen_code_view(report: IntelligenceReport, **kwargs: Any):
    """
    Displays the raw on-screen LLM output, structured JSON, and Gemini thinking traces directly on screen.
    """
    with st.expander("🔍 Raw On-Screen LLM Output & Structured Data", expanded=False):
        tab_md, tab_json, tab_thoughts = st.tabs(["📝 Raw Markdown Output", "📦 Structured Pydantic JSON", "💭 Gemini Thinking Traces"])
        with tab_md:
            st.code(report.formatted_markdown, language="markdown")
        with tab_json:
            st.json(report.model_dump(), expanded=False)
        with tab_thoughts:
            has_thoughts = False
            if report.observability_report and report.observability_report.agent_traces:
                for agent_name, a_trace in report.observability_report.agent_traces.items():
                    all_thoughts = getattr(a_trace, "thinking_traces", None) or []
                    if all_thoughts:
                        has_thoughts = True
                        st.markdown(f"#### 🧠 Agent: `{agent_name}`")
                        for idx, t_text in enumerate(all_thoughts, 1):
                            st.info(f"**Thinking Step #{idx}:**\n\n{t_text}")
            if not has_thoughts:
                st.caption("No thinking traces recorded. (Check that thinking level is not set to 'disabled').")
