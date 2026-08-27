"""
Slack Bolt Application for ADK Real-Time News Intelligence & Scenario Analysis.
Runs in Socket Mode, supporting @bot channel mentions, direct messages,
/news slash commands, real-time in-place status updates, and interactive Block Kit briefings.
"""

import asyncio
import datetime
import logging
import os
import ssl
import sys
from typing import Any, Dict, Optional

import certifi
from dotenv import load_dotenv

load_dotenv()

# Fix macOS Python SSL certificate verification using certifi CA bundle
try:
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    ssl._create_default_https_context = lambda *args, **kwargs: ssl_context
    ssl.create_default_context = lambda *args, **kwargs: ssl_context
except Exception as e:
    pass



from google.genai import types
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from agents.pipeline import build_adk_news_pipeline
from agents.synthesis_agent import format_report_markdown
from config import (
    get_default_model_config,
    get_slack_app_token,
    get_slack_bot_token,
    get_slack_signing_secret,
    validate_slack_config,
)

from observability.tracker import ObservabilityTracker
from schemas.models import (
    BaselineBrief,
    IntelligenceReport,
    InquiryArchetype,
    SafetyCheckResult,
    SearchStageResult,
    SpeculativeInquiry,
    SuppressionStatus,
    SynthesisOutput,
)
from slack_ui import (
    build_executive_report_blocks,
    build_progress_blocks,
    build_report_blocks,
    build_safety_suppression_blocks,
    build_telemetry_modal,
    build_thread_deepdive_blocks,
)
from storage import save_report
from tools.search_tool import consolidate_citations

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("slack_news_bot")

# In-memory cache for recent reports by report_id (allows interactive buttons to access data)
REPORTS_CACHE: Dict[str, IntelligenceReport] = {}

# Agent Name to stage key mapping (supports exact ADK agent names and aliases)
AGENT_MAP = {
    "Safety_Triage_Agent": "safety",
    "Breaking_Fallout_Investigator": "breaking",
    "Precedent_Counter_Investigator": "precedent",
    "Calendar_Filings_Investigator": "calendar",
    "Synthesis_Neutrality_Auditor": "synthesis",
    "SafetyAgent": "safety",
    "BreakingInvestigator": "breaking",
    "PrecedentInvestigator": "precedent",
    "CalendarInvestigator": "calendar",
    "SynthesisAgent": "synthesis",
}

# Initialize Async Bolt App
app = AsyncApp(
    token=get_slack_bot_token() or "xoxb-placeholder",
    signing_secret=get_slack_signing_secret() or "placeholder",
)



def _reconstruct_report_from_state(
    topic: str,
    jurisdiction_str: str,
    state: Dict[str, Any],
    execution_time: float,
    tracker: ObservabilityTracker,
) -> IntelligenceReport:
    """Reconstructs an IntelligenceReport instance from final ADK session state."""
    raw_safety = state.get("safety_result", {})
    safety_res = SafetyCheckResult.model_validate(raw_safety) if raw_safety else SafetyCheckResult()

    raw_stages_1_2 = state.get("stages_1_2", {})
    raw_stages_3_5 = state.get("stages_3_5", {})
    raw_stages_6_7 = state.get("stages_6_7", {})
    raw_synthesis = state.get("synthesis_output", {})

    reconstructed_stages: list[SearchStageResult] = [
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
            stage_name="Analogous Historical Case Studies",
            time_window="All-time",
            objective=f"Structural parallels and base rates for '{topic}'",
            findings_summary=raw_stages_3_5.get("stage5_analogous_summary", "Analogous cases investigated."),
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=6,
            stage_name="Forward Calendar & Catalysts",
            time_window="Next 90 days",
            objective=f"Upcoming deadlines and catalysts for '{topic}'",
            findings_summary=raw_stages_6_7.get("stage6_calendar_summary", "Forward calendar investigated."),
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
        SearchStageResult(
            stage_id=7,
            stage_name="Primary Sources & Filings",
            time_window="Official records",
            objective=f"Statutes, gazettes, regulatory orders for '{topic}'",
            findings_summary=raw_stages_6_7.get("stage7_primary_source_summary", "Primary sources investigated."),
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
    ]

    all_citations = consolidate_citations(reconstructed_stages)

    # Baseline brief & executive summary reconstruction
    baseline_brief = None
    inquiries: list[SpeculativeInquiry] = []
    exec_summary = None
    top_headlines = []
    formatted_md = ""

    if raw_synthesis:
        try:
            synth_obj = SynthesisOutput.model_validate(raw_synthesis)
            exec_summary = synth_obj.executive_summary
            top_headlines = synth_obj.top_headlines
            baseline_brief = synth_obj.baseline_brief
            inquiries = synth_obj.inquiries
            formatted_md = synth_obj.formatted_markdown or ""
        except Exception:
            exec_summary = raw_synthesis.get("executive_summary")
            top_headlines = raw_synthesis.get("top_headlines", [])
            raw_bb = raw_synthesis.get("baseline_brief", {})
            if raw_bb:
                baseline_brief = BaselineBrief(
                    core_event=raw_bb.get("core_event", "Event investigated."),
                    core_event_date=raw_bb.get("core_event_date"),
                    immediate_fallout=raw_bb.get("immediate_fallout", ""),
                    context_precedent=raw_bb.get("context_precedent", ""),
                    evidence_note=raw_bb.get("evidence_note"),
                    top_headlines=raw_bb.get("top_headlines", []),
                )
            raw_inqs = raw_synthesis.get("inquiries", [])
            for item in raw_inqs:
                try:
                    inquiries.append(SpeculativeInquiry.model_validate(item))
                except Exception:
                    pass
            formatted_md = raw_synthesis.get("formatted_markdown", "")

    if not baseline_brief:
        baseline_brief = BaselineBrief(
            core_event=raw_stages_1_2.get("stage1_summary", "Core event investigated across news sources."),
            core_event_date=raw_stages_1_2.get("core_event_date"),
            immediate_fallout=raw_stages_1_2.get("stage2_summary", "Market and institutional reactions analyzed."),
            context_precedent=raw_stages_3_5.get("stage3_precedent_summary", "Historical regulatory context documented."),
            top_headlines=top_headlines,
        )

    # If formatted markdown wasn't generated directly, format it now
    if not formatted_md and baseline_brief:
        formatted_md = format_report_markdown(
            baseline=baseline_brief,
            inquiries=inquiries,
            executive_summary=exec_summary,
            top_headlines=top_headlines,
            safety_notice=safety_res.safety_notice,
            citations=all_citations,
        )

    return IntelligenceReport(
        query_topic=topic,
        jurisdiction=jurisdiction_str,
        executive_summary=exec_summary,
        top_headlines=top_headlines,
        safety_result=safety_res,
        search_stages=reconstructed_stages,
        baseline_brief=baseline_brief,
        inquiries=inquiries,
        citations_all=all_citations,
        formatted_markdown=formatted_md,
        execution_time_seconds=execution_time,
        observability_report=tracker.report,
    )


async def create_slack_canvas(
    client,
    topic: str,
    markdown_content: str,
    channel_id: str,
) -> Optional[str]:
    """
    Creates a standalone Slack Canvas containing the full unconstrained Markdown report,
    and grants read-access to the channel members.
    Returns canvas_id on success, or None on failure/missing scopes.
    """
    if not markdown_content or not markdown_content.strip():
        return None

    try:
        title = f"Intelligence Brief: {topic[:60]}"
        res = await client.canvases_create(
            title=title,
            document_content={
                "type": "markdown",
                "markdown": markdown_content.strip(),
            },
        )
        if not res or not res.get("ok"):
            logger.warning(f"Slack Canvas creation returned non-ok: {res}")
            return None

        canvas_id = res.get("canvas_id")
        logger.info(f"Successfully created Slack Canvas: {canvas_id} for topic: {topic}")

        # Grant read access to the channel
        if canvas_id and channel_id and not channel_id.startswith("D"):
            try:
                await client.canvases_access_set(
                    canvas_id=canvas_id,
                    access_level="read",
                    channel_ids=[channel_id],
                )
            except Exception as e:
                logger.debug(f"Note: Could not explicitly set canvas channel permissions: {e}")

        return canvas_id
    except Exception as e:
        logger.warning(f"Slack Canvas creation skipped (verify 'canvases:write' scope): {e}")
        return None


async def execute_adk_pipeline_for_slack(
    client,
    channel_id: str,
    thread_ts: Optional[str],
    topic: str,
    user_id: str,
    jurisdiction_str: str = "India",
):
    """
    Asynchronously executes the 5-Agent ADK sequential pipeline, streaming
    live progress updates to Slack, and rendering the final Block Kit report.
    """
    logger.info(f"Starting Slack ADK Pipeline for topic: '{topic}' (Channel: {channel_id}, User: {user_id}, Thread: {thread_ts})")

    target_channel = channel_id

    # Auto-join channel if it is a public channel
    if channel_id and channel_id.startswith("C"):
        try:
            await client.conversations_join(channel=channel_id)
        except Exception:
            pass

    statuses = {
        "safety": "running",
        "breaking": "pending",
        "precedent": "pending",
        "calendar": "pending",
        "synthesis": "pending",
    }

    # Post initial live progress message with auto-fallback
    init_blocks = build_progress_blocks(topic, statuses, "Initializing ADK 5-agent sequential pipeline...")
    msg_res = None

    try:
        msg_res = await client.chat_postMessage(
            channel=target_channel,
            thread_ts=thread_ts,
            text=f"🔍 Investigating: {topic}",
            blocks=init_blocks,
        )
    except Exception as e:
        err_str = str(e)
        if "not_in_channel" in err_str and target_channel.startswith("C"):
            try:
                await client.conversations_join(channel=target_channel)
                msg_res = await client.chat_postMessage(
                    channel=target_channel,
                    thread_ts=thread_ts,
                    text=f"🔍 Investigating: {topic}",
                    blocks=init_blocks,
                )
            except Exception as e2:
                logger.error(f"Failed to post after channel join: {e2}")
                return
        elif ("channel_not_found" in err_str or "not_in_channel" in err_str) and user_id:
            try:
                dm_res = await client.conversations_open(users=user_id)
                if dm_res.get("ok"):
                    target_channel = dm_res["channel"]["id"]
                    msg_res = await client.chat_postMessage(
                        channel=target_channel,
                        thread_ts=thread_ts,
                        text=f"🔍 Investigating: {topic}",
                        blocks=init_blocks,
                    )
            except Exception as e3:
                logger.error(f"Failed to open DM conversation: {e3}")
                return
        else:
            logger.error(f"Could not post initial message to Slack: {e}")
            return

    if not msg_res or not msg_res.get("ts"):
        logger.error("No valid message timestamp returned from chat_postMessage.")
        return

    msg_ts = msg_res["ts"]

    start_time = asyncio.get_event_loop().time()
    last_update_time = start_time

    async def update_slack_progress(detail: Optional[str] = None, force: bool = False):
        nonlocal last_update_time
        now = asyncio.get_event_loop().time()
        # Rate limit Slack chat_update to at most once per 1.5 seconds unless forced
        if force or (now - last_update_time >= 1.5):
            last_update_time = now
            try:
                blocks = build_progress_blocks(topic, statuses, detail)
                await client.chat_update(
                    channel=target_channel,
                    ts=msg_ts,
                    text=f"🔍 Investigating: {topic}",
                    blocks=blocks,
                )
            except Exception as e:
                logger.warning(f"Failed to update Slack progress message: {e}")

    try:
        model_cfg = get_default_model_config()
        tracker = ObservabilityTracker(
            topic=topic,
            pipeline_name="NewsIntelligencePipeline",
            max_tool_calls_per_agent=1,
        )


        pipeline_agent, runner, _ = build_adk_news_pipeline(
            model_config=model_cfg,
            jurisdiction=jurisdiction_str,
            tracker=tracker,
        )

        adk_user_id = f"slack_{user_id}"
        session = await runner.session_service.create_session(
            user_id=adk_user_id,
            app_name=runner.app_name,
        )

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

        current_agent_key = "safety"
        last_known_state: Dict[str, Any] = {}

        # Stream ADK Events
        async for event in runner.run_async(
            user_id=adk_user_id,
            session_id=session.id,
            new_message=user_msg,
        ):
            author = getattr(event, "author", None)
            if author:
                # Find matching stage key
                matched_key = AGENT_MAP.get(author)
                if not matched_key:
                    for k_name, s_key in AGENT_MAP.items():
                        if k_name.lower() in author.lower() or s_key in author.lower():
                            matched_key = s_key
                            break

                if matched_key and matched_key != current_agent_key:
                    if current_agent_key:
                        statuses[current_agent_key] = "completed"
                    current_agent_key = matched_key
                    statuses[current_agent_key] = "running"
                    clean_author_name = author.replace("_", " ")
                    await update_slack_progress(f"▶ Agent [{clean_author_name}] running...", force=True)

            # Check for tool call events and streamed thought traces
            if event.content and event.content.parts:
                for p in event.content.parts:
                    fn_call = getattr(p, "function_call", None)
                    if fn_call:
                        tool_name = fn_call.name
                        clean_tool = tool_name.replace("search_stage_", "Stage ").replace("_", " ")
                        await update_slack_progress(f"⚡ Search: {clean_tool}", force=True)

                    is_thought = getattr(p, "thought", False) is True
                    p_text = getattr(p, "text", "") or ""
                    if is_thought and p_text and author:
                        tracker.record_thought(author, p_text)
                        await update_slack_progress(f"🧠 [{author.replace('_', ' ')}] Analyzing evidence...", force=False)

            # Capture latest state
            try:
                cur_session = await runner.session_service.get_session(
                    user_id=adk_user_id,
                    session_id=session.id,
                    app_name=runner.app_name,
                )
                if cur_session and cur_session.state:
                    last_known_state = cur_session.state
            except Exception:
                pass

        # Mark all agents completed
        for k in statuses:
            if statuses[k] == "running":
                statuses[k] = "completed"

        # Final ADK Session State
        final_session = await runner.session_service.get_session(
            user_id=adk_user_id,
            session_id=session.id,
            app_name=runner.app_name,
        )
        state = final_session.state or last_known_state
        execution_time = asyncio.get_event_loop().time() - start_time

        # Check safety suppression
        raw_safety = state.get("safety_result", {})
        safety_res = SafetyCheckResult.model_validate(raw_safety) if raw_safety else SafetyCheckResult()

        if safety_res.status == SuppressionStatus.FULL_SUPPRESSION:
            suppression_blocks = build_safety_suppression_blocks(topic, safety_res)
            await client.chat_update(
                channel=target_channel,
                ts=msg_ts,
                text=f"🚫 Suppressed: {topic}",
                blocks=suppression_blocks,
            )
            return

        # Reconstruct report
        report = _reconstruct_report_from_state(
            topic=topic,
            jurisdiction_str=jurisdiction_str,
            state=state,
            execution_time=execution_time,
            tracker=tracker,
        )

        # Save report to storage
        report_id = save_report(report) or f"rep_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        REPORTS_CACHE[report_id] = report

        # 1. Update main progress message in channel with clean, un-collapsed Executive Briefing & Top Headlines
        exec_blocks = build_executive_report_blocks(report, report_id)
        await client.chat_update(
            channel=target_channel,
            ts=msg_ts,
            text=f"🌐 Intelligence Brief: {topic}",
            blocks=exec_blocks,
        )

        # 2. Automatically post the 10-20 Scenario Projections & Answers with Sources in the thread
        thread_target_ts = thread_ts or msg_ts
        thread_blocks = build_thread_deepdive_blocks(report)
        await client.chat_postMessage(
            channel=target_channel,
            thread_ts=thread_target_ts,
            text=f"🔮 Scenario Analysis & Grounded Inquiries: {topic}",
            blocks=thread_blocks,
        )
        logger.info(f"Successfully posted Slack executive briefing & thread deep-dive for topic: {topic} (Report ID: {report_id})")

    except Exception as e:
        logger.exception(f"Error during Slack ADK execution: {e}")
        error_blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "❌ Investigation Failed", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Topic:* `{topic}`\n*Error:* `{str(e)}`\n\n_Please verify API keys and network connectivity._",
                },
            },
        ]
        await client.chat_update(
            channel=target_channel,
            ts=msg_ts,
            text=f"❌ Error investigating: {topic}",
            blocks=error_blocks,
        )



# ---------------------------------------------------------
# Slack Bolt Event Listeners & Command Handlers
# ---------------------------------------------------------

@app.event("app_mention")
async def handle_app_mentions(body: Dict[str, Any], client):
    """
    Handles @NewsBot channel mentions.
    e.g. '@NewsBot Analyze TSMC tariff impact on semiconductor equities'
    """
    event = body.get("event", {})
    text = event.get("text", "")
    channel_id = event.get("channel")
    user_id = event.get("user", "slack_user")
    thread_ts = event.get("thread_ts") or event.get("ts")

    # Strip bot mention tag (<@Uxxxx>)
    query = " ".join([w for w in text.split() if not (w.startswith("<@") and w.endswith(">"))]).strip()

    if not query:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="👋 Please specify a topic or breaking news inquiry, e.g. `@NewsBot RBI liquidity infusion impact on banking sector`",
        )
        return

    # Run ADK pipeline in background task
    asyncio.create_task(
        execute_adk_pipeline_for_slack(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            topic=query,
            user_id=user_id,
        )
    )


@app.event("message")
async def handle_direct_messages(body: Dict[str, Any], client):
    """
    Handles 1-on-1 Direct Messages (DMs) with the bot.
    """
    event = body.get("event", {})
    channel_type = event.get("channel_type")
    subtype = event.get("subtype")
    text = event.get("text", "").strip()
    channel_id = event.get("channel")
    user_id = event.get("user", "slack_user")
    thread_ts = event.get("thread_ts")

    # Only process incoming user DMs (ignore bot responses and channel messages handled by app_mention)
    if channel_type == "im" and not subtype and text:
        asyncio.create_task(
            execute_adk_pipeline_for_slack(
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                topic=text,
                user_id=user_id,
            )
        )


@app.command("/news")
async def handle_news_command(ack, body: Dict[str, Any], client):
    """
    Handles the /news <topic> slash command.
    """
    await ack()
    topic = body.get("text", "").strip()
    channel_id = body.get("channel_id")
    user_id = body.get("user_id", "slack_user")

    if not topic:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="⚠️ Please specify a news topic. Example: `/news Adani port expansion regulatory clearance`",
        )
        return

    asyncio.create_task(
        execute_adk_pipeline_for_slack(
            client=client,
            channel_id=channel_id,
            thread_ts=None,
            topic=topic,
            user_id=user_id,
        )
    )


# ---------------------------------------------------------
# Interactive Action Handlers (Block Kit Buttons)
# ---------------------------------------------------------

@app.action("slack_action_save_report")
async def handle_save_report_action(ack, body: Dict[str, Any], client):
    """Handles the '💾 Save Briefing' button click."""
    await ack()
    action = body.get("actions", [{}])[0]
    report_id = action.get("value", "")
    channel_id = body.get("channel", {}).get("id")
    message_ts = body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id")

    report = REPORTS_CACHE.get(report_id)
    if report:
        saved_stem = save_report(report)
        msg_text = f"✅ <@{user_id}> successfully saved this intelligence briefing to storage (`{saved_stem or report_id}`)."
    else:
        msg_text = f"💾 Briefing is recorded in local history (`{report_id}`)."

    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=msg_text,
    )


@app.action("slack_action_view_telemetry")
async def handle_view_telemetry_action(ack, body: Dict[str, Any], client):
    """Handles the '📊 Observability & Sources' button click (Opens Modal)."""
    await ack()
    action = body.get("actions", [{}])[0]
    report_id = action.get("value", "")
    trigger_id = body.get("trigger_id")
    channel_id = body.get("channel", {}).get("id")
    message_ts = body.get("message", {}).get("ts")

    report = REPORTS_CACHE.get(report_id)
    if report and trigger_id:
        try:
            modal_view = build_telemetry_modal(report)
            await client.views_open(
                trigger_id=trigger_id,
                view=modal_view,
            )
            return
        except Exception as e:
            logger.warning(f"Could not open telemetry modal: {e}")

    # Fallback to posting in thread
    if report:
        exec_s = f"{report.execution_time_seconds:.2f}s" if report.execution_time_seconds else "N/A"
        sources_cnt = len(report.citations_all)
        stages_cnt = len(report.search_stages)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=(
                f"📊 *Observability Snapshot:*\n"
                f"• Execution Time: `{exec_s}`\n"
                f"• Search Stages: `{stages_cnt}/7`\n"
                f"• Consolidated Sources: `{sources_cnt}` URLs\n"
                f"• Jurisdiction: `{report.jurisdiction}`"
            ),
        )


@app.action("slack_action_feedback_positive")
async def handle_feedback_positive(ack, body: Dict[str, Any], client):
    """Handles '👍 Helpful' button click."""
    await ack()
    user_id = body.get("user", {}).get("id")
    channel_id = body.get("channel", {}).get("id")
    message_ts = body.get("message", {}).get("ts")
    logger.info(f"Received positive feedback from user {user_id}")
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=f"👍 <@{user_id}> marked this briefing as helpful!",
    )


@app.action("slack_action_feedback_negative")
async def handle_feedback_negative(ack, body: Dict[str, Any], client):
    """Handles '👎 Irrelevant' button click."""
    await ack()
    user_id = body.get("user", {}).get("id")
    channel_id = body.get("channel", {}).get("id")
    message_ts = body.get("message", {}).get("ts")
    logger.info(f"Received negative feedback from user {user_id}")
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=f"👎 Feedback recorded from <@{user_id}>. Future research will adjust search weights.",
    )


@app.action("slack_action_open_canvas")
async def handle_open_canvas_action(ack, body: Dict[str, Any], client):
    """Acknowledges canvas link clicks."""
    await ack()


# ---------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------

async def start_slack_bot():
    """Validates configuration and launches the Slack Bolt Socket Mode Handler."""
    is_valid, err_msg = validate_slack_config(require_app_token=True)
    if not is_valid:
        print(f"\n❌ [Slack Config Error] {err_msg}")
        print("➡️  Please add SLACK_BOT_TOKEN and SLACK_APP_TOKEN to your .env file.")
        print("➡️  Refer to slack_manifest.json to set up your Slack App on https://api.slack.com/apps\n")
        return

    # Re-apply resolved bot token in case environment was loaded late
    app._token = get_slack_bot_token()
    app._client = None  # Force re-instantiation of client with new token

    handler = AsyncSocketModeHandler(app, get_slack_app_token())
    print("\n" + "=" * 65)
    print("⚡ ADK News Intelligence Slack Bot running in Socket Mode...")
    print("👂 Listening for @bot mentions, DMs, and /news commands...")
    print("=" * 65 + "\n")
    await handler.start_async()



def main():
    try:
        asyncio.run(start_slack_bot())
    except KeyboardInterrupt:
        print("\n🛑 Slack Bot stopped by user.")


if __name__ == "__main__":
    main()
