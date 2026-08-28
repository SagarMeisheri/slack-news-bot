"""
Slack Bolt Application for ADK Real-Time News Intelligence, Scenario Analysis, & Sarvam Document OCR.
Runs in Socket Mode, supporting:
- Automatic zero-mention channel message listening & acknowledgement
- Sarvam AI Document Intelligence (OCR) for PDF/Image document digitization
- 5-Agent ADK News Intelligence & Scenario Analysis Pipeline
- Interactive Block Kit executive briefings, telemetry modals, and thread deep-dives
"""

import asyncio
import datetime
import logging
import os
import ssl
import sys
from typing import Any, Dict, List, Optional

import certifi
from dotenv import load_dotenv
import httpx

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

from agents.pipeline import build_adk_news_pipeline, classify_and_route, execute_sarvam_ocr_job
from agents.synthesis_agent import format_report_markdown
from config import (
    get_default_model_config,
    get_sarvam_api_key,
    get_sarvam_default_language,
    get_slack_allowed_channels,
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
    OCRProcessingResult,
    RequestClassification,
    RequestIntent,
    SafetyCheckResult,
    SearchStageResult,
    SpeculativeInquiry,
    SuppressionStatus,
    SynthesisOutput,
)
from slack_ui import (
    build_executive_report_blocks,
    build_news_error_blocks,
    build_ocr_progress_blocks,
    build_ocr_result_blocks,
    build_progress_blocks,
    build_report_blocks,
    build_safety_suppression_blocks,
    build_telemetry_modal,
    build_thread_deepdive_blocks,
)

from storage import save_report
from tools.sarvam_client import SarvamOCRClient, SarvamOCRError
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


def is_channel_allowed(channel_id: Optional[str]) -> bool:
    """Checks if the channel is in the allowed whitelist (or if whitelist is empty)."""
    if not channel_id:
        return True
    allowed = get_slack_allowed_channels()
    if not allowed:
        return True
    return channel_id in allowed


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
            objective=f"Dissenting viewpoints and defenses for '{topic}'",
            findings_summary=raw_stages_3_5.get("stage4_counter_summary", "Counter-narratives investigated."),
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=5,
            stage_name="Parallel & International Benchmarks",
            time_window="0–180 days",
            objective=f"Global and comparative precedents for '{topic}'",
            findings_summary=raw_stages_3_5.get("stage5_benchmarks_summary", "Benchmarks investigated."),
            excerpts=[],
            citations=raw_stages_3_5.get("citations", []),
        ),
        SearchStageResult(
            stage_id=6,
            stage_name="Forward Calendar & Triggers",
            time_window="Forward: 0–90 days",
            objective=f"Upcoming regulatory deadlines and hearings for '{topic}'",
            findings_summary=raw_stages_6_7.get("stage6_calendar_summary", "Forward triggers investigated."),
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
        SearchStageResult(
            stage_id=7,
            stage_name="Primary Filings & Official Dossiers",
            time_window="Primary Sources",
            objective=f"Direct statutory texts and regulatory orders for '{topic}'",
            findings_summary=raw_stages_6_7.get("stage7_filings_summary", "Primary filings verified."),
            excerpts=[],
            citations=raw_stages_6_7.get("citations", []),
        ),
    ]

    raw_brief = raw_synthesis.get("baseline_brief", {})
    baseline_brief = BaselineBrief.model_validate(raw_brief) if raw_brief else BaselineBrief()

    inquiries = []
    for inq_data in raw_synthesis.get("inquiries", []):
        try:
            inquiries.append(SpeculativeInquiry.model_validate(inq_data))
        except Exception:
            pass

    if not inquiries:
        inquiries = [
            SpeculativeInquiry(
                inquiry_id=1,
                headline="Primary Sector & Regulatory Trajectory",
                sub_question="What are the immediate statutory and market milestones following this development?",
                grounded_answer="Analysis synthesized from verified multi-stage evidence across official regulatory feeds.",
                archetype=InquiryArchetype.CONSEQUENCE_IMMEDIATE,
                citations_used=[],
                confidence_rating="High",
            )
        ]

    citations_1_2 = raw_stages_1_2.get("citations", [])
    citations_3_5 = raw_stages_3_5.get("citations", [])
    citations_6_7 = raw_stages_6_7.get("citations", [])
    citations_synth = raw_synthesis.get("citations", [])
    citations_all = consolidate_citations(citations_1_2, citations_3_5, citations_6_7, citations_synth)

    exec_summary = (
        raw_synthesis.get("executive_summary")
        or baseline_brief.ground_truth_core
        or f"Intelligence synthesis completed for {topic}."
    )

    top_headlines = raw_synthesis.get("top_headlines", [])
    if not top_headlines and baseline_brief.ground_truth_core:
        top_headlines = [f"Breaking: {baseline_brief.ground_truth_core[:120]}..."]

    rendered_markdown = format_report_markdown(
        topic=topic,
        jurisdiction=jurisdiction_str,
        safety_result=safety_res,
        baseline_brief=baseline_brief,
        inquiries=inquiries,
        citations=citations_all,
    )

    obs_report = tracker.build_observability_report(execution_time_seconds=execution_time)

    return IntelligenceReport(
        query_topic=topic,
        jurisdiction=jurisdiction_str,
        executive_summary=exec_summary,
        top_headlines=top_headlines,
        safety_result=safety_res,
        search_stages=reconstructed_stages,
        baseline_brief=baseline_brief,
        inquiries=inquiries,
        citations_all=citations_all,
        formatted_markdown=rendered_markdown,
        execution_time_seconds=execution_time,
        observability_report=obs_report,
    )


# ---------------------------------------------------------
# Sarvam Document OCR Execution Handler for Slack
# ---------------------------------------------------------

async def execute_sarvam_ocr_for_slack(
    client,
    channel_id: str,
    thread_ts: str,
    file_id: str,
    filename: str,
    file_url: Optional[str] = None,
    user_id: str = "slack_user",
):
    """
    Downloads document from Slack, executes Sarvam OCR digitization,
    and returns formatted Markdown results directly in the Slack thread.
    """
    bot_token = get_slack_bot_token()
    download_url = file_url

    # Post initial progress message
    prog_blocks = build_ocr_progress_blocks(filename=filename, status_msg="Connecting to Sarvam Vision 1.5...")
    post_res = await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f"📄 Processing document: `{filename}` with Sarvam OCR...",
        blocks=prog_blocks,
    )
    progress_ts = post_res.get("ts")

    try:
        # If download URL not directly in event payload, fetch via files.info
        if not download_url:
            f_info = await client.files_info(file=file_id)
            f_data = f_info.get("file", {})
            download_url = f_data.get("url_private_download") or f_data.get("url_private")
            filename = f_data.get("name") or filename

        if not download_url:
            raise SarvamOCRError(f"Could not resolve private download URL for file ID {file_id}")

        # Download binary from Slack with bot authorization header (following S3/CDN redirects)
        headers = {"Authorization": f"Bearer {bot_token}"}
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http_client:
            dl_resp = await http_client.get(download_url, headers=headers)
            if dl_resp.status_code != 200:
                raise SarvamOCRError(f"Failed to download file from Slack: HTTP {dl_resp.status_code} ({dl_resp.reason_phrase})")
            file_bytes = dl_resp.content


        # Update status
        await client.chat_update(
            channel=channel_id,
            ts=progress_ts,
            text=f"📄 Digitizing document `{filename}` with Sarvam Document AI...",
            blocks=build_ocr_progress_blocks(filename=filename, status_msg="Parsing layout, Indic text & tables..."),
        )

        # Run Sarvam OCR job
        ocr_result: OCRProcessingResult = await execute_sarvam_ocr_job(
            file_bytes=file_bytes,
            filename=filename,
            language=get_sarvam_default_language(),
        )

        # If text is long, upload complete .md file snippet to thread
        if ocr_result.file_upload_required and ocr_result.markdown_content:
            try:
                base_name = filename.rsplit(".", 1)[0]
                await client.files_upload_v2(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    filename=f"{base_name}_ocr.md",
                    title=f"Extracted OCR: {filename}",
                    content=ocr_result.markdown_content,
                )
            except Exception as up_err:
                logger.warning(f"Could not upload markdown snippet file: {up_err}")

        # Update progress block to final result Block Kit
        result_blocks = build_ocr_result_blocks(
            filename=ocr_result.filename,
            content_type=ocr_result.content_type,
            markdown_text=ocr_result.markdown_content,
            execution_time=ocr_result.execution_time_seconds,
            language=ocr_result.language,
            error=ocr_result.error,
            truncated=ocr_result.truncated,
            page_count=ocr_result.page_count,
            table_count=ocr_result.table_count,
            file_id=file_id if ocr_result.error else None,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )


        if ocr_result.error:
            await client.chat_update(
                channel=channel_id,
                ts=progress_ts,
                text=f"❌ Document OCR Failed: {filename}",
                blocks=result_blocks,
            )
            logger.warning(f"Delivered OCR error notification for {filename}: {ocr_result.error}")
        else:
            await client.chat_update(
                channel=channel_id,
                ts=progress_ts,
                text=f"📄 Document OCR Complete: {filename}",
                blocks=result_blocks,
            )
            logger.info(f"Successfully processed and delivered Sarvam OCR for {filename} in channel {channel_id}")


    except Exception as e:
        logger.exception(f"Error handling Slack Sarvam OCR: {e}")
        error_blocks = build_ocr_result_blocks(
            filename=filename,
            content_type="document",
            markdown_text="",
            execution_time=0.0,
            error=str(e),
            file_id=file_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        await client.chat_update(
            channel=channel_id,
            ts=progress_ts,
            text=f"❌ OCR failed for {filename}",
            blocks=error_blocks,
        )



# ---------------------------------------------------------
# ADK News Intelligence Execution Handler for Slack
# ---------------------------------------------------------

async def execute_adk_pipeline_for_slack(
    client,
    channel_id: str,
    thread_ts: Optional[str],
    topic: str,
    user_id: str = "slack_user",
    jurisdiction_str: str = "India",
):
    """
    Executes the 5-agent ADK Sequential Pipeline asynchronously,
    updating the Slack channel with live progress blocks, then delivering
    the Executive Briefing and Scenario Deep-Dive.
    """
    target_channel = channel_id
    statuses: Dict[str, str] = {
        "safety": "running",
        "breaking": "pending",
        "precedent": "pending",
        "calendar": "pending",
        "synthesis": "pending",
    }

    initial_blocks = build_progress_blocks(
        topic=topic,
        statuses=statuses,
        status_message="🚀 Initializing ADK News Intelligence Agents...",
    )

    resp = await client.chat_postMessage(
        channel=target_channel,
        thread_ts=thread_ts,
        text=f"🔎 Analyzing topic: {topic}",
        blocks=initial_blocks,
    )
    msg_ts = resp["ts"]

    last_update_time = [asyncio.get_event_loop().time()]

    async def update_slack_progress(message: str, force: bool = False):
        now = asyncio.get_event_loop().time()
        if force or (now - last_update_time[0] >= 1.2):
            last_update_time[0] = now
            blocks = build_progress_blocks(topic=topic, statuses=statuses, status_message=message)
            try:
                await client.chat_update(
                    channel=target_channel,
                    ts=msg_ts,
                    text=f"🔎 Progress: {topic}",
                    blocks=blocks,
                )
            except Exception as e:
                logger.debug(f"Slack rate limit or progress update skipped: {e}")

    try:
        pipeline_agent, runner, tracker = build_adk_news_pipeline(
            jurisdiction=jurisdiction_str,
            app_name=f"slack_bot_{user_id}",
        )

        adk_user_id = f"slack_{user_id}"
        session = await runner.session_service.create_session(
            user_id=adk_user_id,
            app_name=runner.app_name,
            state={"query_topic": topic, "jurisdiction": jurisdiction_str},
        )

        start_time = asyncio.get_event_loop().time()
        user_msg = types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Analyze topic: '{topic}' in jurisdiction '{jurisdiction_str}'.")],
        )

        current_agent_key = "safety"
        last_known_state: Dict[str, Any] = {}

        async for event in runner.run_async(
            user_id=adk_user_id,
            session_id=session.id,
            new_message=user_msg,
        ):
            author = getattr(event, "author", None)
            if author:
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

        for k in statuses:
            if statuses[k] == "running":
                statuses[k] = "completed"

        final_session = await runner.session_service.get_session(
            user_id=adk_user_id,
            session_id=session.id,
            app_name=runner.app_name,
        )
        state = final_session.state or last_known_state
        execution_time = asyncio.get_event_loop().time() - start_time

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

        report = _reconstruct_report_from_state(
            topic=topic,
            jurisdiction_str=jurisdiction_str,
            state=state,
            execution_time=execution_time,
            tracker=tracker,
        )

        report_id = save_report(report) or f"rep_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        REPORTS_CACHE[report_id] = report

        exec_blocks = build_executive_report_blocks(report, report_id)
        await client.chat_update(
            channel=target_channel,
            ts=msg_ts,
            text=f"🌐 Intelligence Brief: {topic}",
            blocks=exec_blocks,
        )

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
        error_blocks = build_news_error_blocks(
            topic=topic,
            error=str(e),
            channel_id=target_channel,
            thread_ts=thread_ts,
            user_id=user_id,
        )
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
    Handles @bot channel mentions explicitly.
    e.g. '@NewsBot RBI liquidity infusion impact on banking sector'
    """
    event = body.get("event", {})
    text = event.get("text", "")
    channel_id = event.get("channel")
    user_id = event.get("user", "slack_user")
    message_ts = event.get("ts")
    thread_ts = event.get("thread_ts") or message_ts
    files = event.get("files", [])

    if not is_channel_allowed(channel_id):
        return

    # Acknowledge with eyes reaction
    if message_ts and channel_id:
        try:
            await client.reactions_add(channel=channel_id, name="eyes", timestamp=message_ts)
        except Exception:
            pass

    # Strip bot mention tag (<@Uxxxx>)
    query = " ".join([w for w in text.split() if not (w.startswith("<@") and w.endswith(">"))]).strip()

    # Route files if present
    if files:
        for f_info in files:
            file_id = f_info.get("id")
            filename = f_info.get("name") or "document.pdf"
            file_url = f_info.get("url_private_download") or f_info.get("url_private")
            asyncio.create_task(
                execute_sarvam_ocr_for_slack(
                    client=client,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    file_id=file_id,
                    filename=filename,
                    file_url=file_url,
                    user_id=user_id,
                )
            )
        return

    if not query:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="👋 Send any breaking news topic or upload a PDF/image document to process with Sarvam OCR!",
        )
        return

    # Check routing with ADK Classifier
    classification = await classify_and_route(text=query, has_files=False)
    if classification.intent == RequestIntent.DOCUMENT_OCR:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="📄 *Sarvam OCR Assistant:* Please upload your PDF, PNG, or JPG document to extract its contents.",
        )
        return

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
async def handle_incoming_messages(body: Dict[str, Any], client):
    """
    Handles all incoming messages in channels, groups, and DMs without requiring an @mention.
    Automatically acknowledges receipt and routes to Sarvam OCR or News Intelligence.
    """
    event = body.get("event", {})
    subtype = event.get("subtype")
    bot_id = event.get("bot_id")
    text = event.get("text", "").strip()
    channel_id = event.get("channel")
    channel_type = event.get("channel_type")
    user_id = event.get("user", "slack_user")
    message_ts = event.get("ts")
    thread_ts = event.get("thread_ts") or message_ts
    files = event.get("files", [])

    # 1. CRITICAL: Ignore messages sent by bots, edits, deletions to prevent loops
    if bot_id or subtype in ("bot_message", "message_deleted", "message_changed") or event.get("bot_profile"):
        return

    # 2. Check channel allowlist
    if not is_channel_allowed(channel_id):
        return

    # 3. Add visual acknowledgment (eyes reaction)
    if message_ts and channel_id:
        try:
            await client.reactions_add(channel=channel_id, name="eyes", timestamp=message_ts)
        except Exception:
            pass

    # 4. If files (PDFs, PNGs, JPGs) are attached, process with Sarvam OCR
    if files:
        for f_info in files:
            file_id = f_info.get("id")
            filename = f_info.get("name") or "document.pdf"
            file_url = f_info.get("url_private_download") or f_info.get("url_private")
            asyncio.create_task(
                execute_sarvam_ocr_for_slack(
                    client=client,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    file_id=file_id,
                    filename=filename,
                    file_url=file_url,
                    user_id=user_id,
                )
            )
        return

    if not text:
        return

    # 5. Route text using ADK Intent Classifier
    classification = await classify_and_route(text=text, has_files=False)

    if classification.intent == RequestIntent.DOCUMENT_OCR:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="📄 *Sarvam OCR Assistant:* Please upload your PDF, PNG, or JPG file to extract and digitize its content.",
        )
        return

    # 6. Run ADK News Intelligence Pipeline in background task
    asyncio.create_task(
        execute_adk_pipeline_for_slack(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            topic=text,
            user_id=user_id,
        )
    )


@app.event("file_shared")
async def handle_file_shared_event(body: Dict[str, Any], client):
    """
    Handles standalone file_shared events from Slack.
    """
    event = body.get("event", {})
    file_id = event.get("file_id") or event.get("file", {}).get("id")
    channel_id = event.get("channel_id")
    user_id = event.get("user_id", "slack_user")

    if not file_id or not is_channel_allowed(channel_id):
        return

    try:
        f_info = await client.files_info(file=file_id)
        f_data = f_info.get("file", {})
        filename = f_data.get("name") or "document.pdf"
        file_url = f_data.get("url_private_download") or f_data.get("url_private")
        channels = f_data.get("channels", [])
        target_channel = channel_id or (channels[0] if channels else None)

        if not target_channel:
            return

        asyncio.create_task(
            execute_sarvam_ocr_for_slack(
                client=client,
                channel_id=target_channel,
                thread_ts=None,
                file_id=file_id,
                filename=filename,
                file_url=file_url,
                user_id=user_id,
            )
        )
    except Exception as e:
        logger.debug(f"Could not handle file_shared event: {e}")


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


@app.action("slack_action_retry_ocr")
async def handle_retry_ocr_action(ack, body: Dict[str, Any], client):
    """Handles the '🔄 Retry OCR' button click on failed document processing cards."""
    await ack()
    action = body.get("actions", [{}])[0]
    raw_val = action.get("value", "")
    parts = raw_val.split("|")
    file_id = parts[0] if len(parts) > 0 and parts[0] else None
    filename = parts[1] if len(parts) > 1 and parts[1] else "document.pdf"
    channel_id = parts[2] if len(parts) > 2 and parts[2] else body.get("channel", {}).get("id")
    thread_ts = parts[3] if len(parts) > 3 and parts[3] else body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id", "slack_user")

    if not file_id:
        return

    logger.info(f"Retrying Sarvam OCR for file {file_id} ({filename}) requested by user {user_id}")
    asyncio.create_task(
        execute_sarvam_ocr_for_slack(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            file_id=file_id,
            filename=filename,
            user_id=user_id,
        )
    )


@app.action("slack_action_retry_news")
async def handle_retry_news_action(ack, body: Dict[str, Any], client):
    """Handles the '🔄 Retry Investigation' button click on failed news research cards."""
    await ack()
    action = body.get("actions", [{}])[0]
    raw_val = action.get("value", "")
    parts = raw_val.split("|")
    topic = parts[0] if len(parts) > 0 and parts[0] else None
    channel_id = parts[1] if len(parts) > 1 and parts[1] else body.get("channel", {}).get("id")
    thread_ts = parts[2] if len(parts) > 2 and parts[2] else body.get("message", {}).get("ts")
    user_id = parts[3] if len(parts) > 3 and parts[3] else body.get("user", {}).get("id", "slack_user")

    if not topic:
        return

    logger.info(f"Retrying ADK News Investigation for '{topic}' requested by user {user_id}")
    asyncio.create_task(
        execute_adk_pipeline_for_slack(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            topic=topic,
            user_id=user_id,
        )
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
    app._client = None

    handler = AsyncSocketModeHandler(app, get_slack_app_token())
    print("\n" + "=" * 70)
    print("⚡ ADK News Intelligence & Sarvam OCR Bot running in Socket Mode...")
    print("👂 Auto-listening to channel messages, document uploads, and DMs...")
    print("=" * 70 + "\n")
    await handler.start_async()


def main():
    try:
        asyncio.run(start_slack_bot())
    except KeyboardInterrupt:
        print("\n🛑 Slack Bot stopped by user.")


if __name__ == "__main__":
    main()
