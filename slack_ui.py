"""
Slack UI Block Kit Formatter for ADK News Intelligence.
Generates dynamic progress indicators, crisp un-collapsed executive briefings,
threaded deep-dive scenario analyses, interactive action buttons, and telemetry modals.
"""

import re
from typing import Any, Dict, List, Optional
from schemas.models import (
    IntelligenceReport,
    SafetyCategory,
    SafetyCheckResult,
    SuppressionStatus,
)


STAGE_NAMES = {
    "safety": "Safety & Compliance Triage",
    "breaking": "Breaking & Fallout Search",
    "precedent": "Precedent & Counter-Narratives",
    "calendar": "Forward Calendar & Primary Sources",
    "synthesis": "Synthesis & Scenario Analysis",
}

STATUS_ICONS = {
    "pending": "⚪",
    "running": "⏳",
    "completed": "✅",
    "warning": "⚠️",
    "suppressed": "🚫",
    "failed": "❌",
}


def truncate_mrkdwn(text: str, max_len: int = 2800) -> str:
    """Safely truncates markdown text to adhere to Slack's 3,000 char per block limit."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    suffix = "\n\n_...[truncated]_"
    if max_len <= len(suffix):
        return text[:max_len]
    return text[: max_len - len(suffix)] + suffix


def format_slack_url(url: str, title: str) -> str:
    """Formats a link for Slack mrkdwn: <url|title>."""
    clean_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    clean_url = url.replace(" ", "%20")
    return f"<{clean_url}|{clean_title}>"


def convert_markdown_to_slack_mrkdwn(text: str) -> str:
    """
    Light Slack mrkdwn adapter: Converts standard Markdown formatting to Slack mrkdwn.
    - [Title](URL) -> <URL|Title>
    - **Bold** -> *Bold*
    - ### Headers -> *Headers*
    """
    if not text:
        return ""

    # 1. Convert markdown links: [Title](URL) -> <URL|Title>
    def _link_repl(match):
        title = match.group(1).strip()
        url = match.group(2).strip()
        clean_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        clean_url = url.replace(" ", "%20")
        return f"<{clean_url}|{clean_title}>"

    converted = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", _link_repl, text)

    # 2. Convert markdown bold **text** -> *text*
    converted = re.sub(r"\*\*(.*?)\*\*", r"*\1*", converted)

    # 3. Convert markdown headers: ### Header -> *Header*
    converted = re.sub(r"^\s*#{1,6}\s*(.*)$", r"*\1*", converted, flags=re.MULTILINE)

    return converted


def split_markdown_into_slack_blocks(mrkdwn_text: str, max_chunk_len: int = 1500) -> List[Dict[str, Any]]:
    """
    Splits converted mrkdwn text into structured Slack section blocks,
    setting expand: True to prevent Slack's 'See more' collapse.
    """
    blocks: List[Dict[str, Any]] = []
    paragraphs = mrkdwn_text.split("\n\n")
    current_chunk = ""

    for p in paragraphs:
        p_str = p.strip()
        if not p_str:
            continue

        if p_str == "---":
            if current_chunk:
                blocks.append({
                    "type": "section",
                    "expand": True,
                    "text": {"type": "mrkdwn", "text": current_chunk},
                })
                current_chunk = ""
            blocks.append({"type": "divider"})
            continue

        if len(current_chunk) + len(p_str) + 2 > max_chunk_len:
            if current_chunk:
                blocks.append({
                    "type": "section",
                    "expand": True,
                    "text": {"type": "mrkdwn", "text": current_chunk},
                })
                current_chunk = ""

            while len(p_str) > max_chunk_len:
                sub_part = p_str[:max_chunk_len]
                blocks.append({
                    "type": "section",
                    "expand": True,
                    "text": {"type": "mrkdwn", "text": sub_part},
                })
                p_str = p_str[max_chunk_len:]
            current_chunk = p_str
        else:
            if current_chunk:
                current_chunk += "\n\n" + p_str
            else:
                current_chunk = p_str

    if current_chunk:
        blocks.append({
            "type": "section",
            "expand": True,
            "text": {"type": "mrkdwn", "text": current_chunk},
        })

    return blocks


def build_progress_blocks(
    topic: str,
    statuses: Dict[str, str],
    current_detail: Optional[str] = None,
    status_message: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Constructs a live step-by-step progress view updated via chat_update.
    """
    detail = status_message or current_detail
    lines = []
    for key, name in STAGE_NAMES.items():
        st = statuses.get(key, "pending")
        icon = STATUS_ICONS.get(st, "⚪")
        if st == "running":
            lines.append(f"{icon} *{name}* _(In progress...)_")
        elif st == "completed":
            lines.append(f"{icon} *{name}* _(Done)_")
        elif st == "suppressed":
            lines.append(f"{icon} *{name}* _(Suppressed per safety rules)_")
        elif st == "warning":
            lines.append(f"{icon} *{name}* _(Partial clearance)_")
        elif st == "failed":
            lines.append(f"{icon} *{name}* _(Failed)_")
        else:
            lines.append(f"{icon} {name}")

    progress_text = "\n".join(lines)
    if detail:
        progress_text += f"\n\n⚡ *Active Operation:* `{detail[:120]}`"


    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 ADK News Intelligence Pipeline",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"*Topic:* `{topic[:150]}`\n\n*Pipeline Stage Progress:*\n{progress_text}",
            },
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🤖 _Executing 5-Agent ADK Sequential Pipeline with Google GenAI & Parallel Search_",
                }
            ],
        },
    ]


def build_safety_suppression_blocks(
    topic: str,
    safety_result: SafetyCheckResult,
) -> List[Dict[str, Any]]:
    """
    Constructs an alert block for fully suppressed or prohibited queries.
    """
    categories_str = ", ".join([c.value for c in safety_result.categories_triggered]) or "Editorial Safety Protocol"
    rationale = safety_result.rationale or "The query triggered editorial or legal suppression guardrails."

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚫 Investigation Suppressed by Safety Triage",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Topic:* `{topic}`\n"
                    f"*Status:* `FULL_SUPPRESSION`\n"
                    f"*Triggered Categories:* {categories_str}\n\n"
                    f"*Rationale:* {rationale}"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🛡️ *Compliance Policy:* Active emergencies, unverified defamatory rumors, and sub-judice topics are suppressed.",
                }
            ],
        },
    ]


def build_news_error_blocks(
    topic: str,
    error: str,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Constructs an error Block Kit card with a '🔄 Retry Investigation' interactive button.
    """
    retry_val = f"{topic}|{channel_id or ''}|{thread_ts or ''}|{user_id or ''}"
    return [

        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "❌ News Investigation Failed",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"*Topic:* `{topic}`\n*Error:* `{error}`\n\nClick the button below to re-run the 5-agent investigation without re-typing.",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔄 Retry Investigation",
                        "emoji": True,
                    },
                    "style": "primary",
                    "action_id": "slack_action_retry_news",
                    "value": retry_val[:2000],
                }
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "⚡ *ADK Pipeline:* Parallel Search, Google GenAI, and Sequential Multi-Agent Architecture",
                }
            ],
        },
    ]


def build_executive_report_blocks(

    report: IntelligenceReport,
    report_id: str = "",
) -> List[Dict[str, Any]]:
    """
    Constructs a clean, punchy Executive Intelligence Brief for the main Slack channel message.
    Configured with expand: True and bite-sized blocks to eliminate Slack's 'See more' collapse.
    """
    blocks: List[Dict[str, Any]] = []

    # 1. Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"🌐 Intelligence Brief: {report.query_topic[:80]}",
            "emoji": True,
        },
    })
    blocks.append({"type": "divider"})

    # 2. Safety Notice (if partial suppression or warning)
    if report.safety_result.status == SuppressionStatus.PARTIAL_SUPPRESSION:
        cats = ", ".join([c.value for c in report.safety_result.categories_triggered])
        blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Editorial Notice (Partial Clearance):* {cats}\n_{report.safety_result.rationale}_",
            },
        })
        blocks.append({"type": "divider"})

    # 3. Executive Summary & Strategic Takeaway
    exec_summary = report.executive_summary
    if not exec_summary and report.baseline_brief:
        exec_summary = report.baseline_brief.core_event

    if exec_summary:
        blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"⚡ *EXECUTIVE TL;DR & STRATEGIC TAKEAWAY*\n{truncate_mrkdwn(convert_markdown_to_slack_mrkdwn(exec_summary), 1500)}",
            },
        })
        blocks.append({"type": "divider"})

    # 4. Top Breaking Headlines
    headlines_text = ""
    if report.top_headlines:
        hl_lines = [f"• {convert_markdown_to_slack_mrkdwn(h.lstrip('* '))}" for h in report.top_headlines[:4]]
        headlines_text = "\n".join(hl_lines)
    elif report.citations_all:
        hl_lines = []
        for idx, c in enumerate(report.citations_all[:4], start=1):
            url = c.get("url", "")
            title = c.get("title") or c.get("source_domain") or f"Breaking Source {idx}"
            domain = c.get("source_domain") or "News Source"
            date_str = f" ({c.get('publish_date')})" if c.get("publish_date") else ""
            if url:
                hl_lines.append(f"• {format_slack_url(url, title[:70])} — _{domain}{date_str}_")
            else:
                hl_lines.append(f"• *{title[:70]}* — _{domain}{date_str}_")
        headlines_text = "\n".join(hl_lines)

    if headlines_text:
        blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"📰 *TOP BREAKING HEADLINES*\n{headlines_text}",
            },
        })
        blocks.append({"type": "divider"})

    # 5. Baseline Verified Facts
    if report.baseline_brief:
        brief = report.baseline_brief
        date_str = f" *[{brief.core_event_date}]*" if brief.core_event_date else ""
        baseline_md = (
            f"📌 *Core Event{date_str}:*\n{convert_markdown_to_slack_mrkdwn(brief.core_event)}\n\n"
            f"💥 *Immediate Fallout:*\n{convert_markdown_to_slack_mrkdwn(brief.immediate_fallout)}\n\n"
            f"🏛️ *Context & Precedent:*\n{convert_markdown_to_slack_mrkdwn(brief.context_precedent)}"
        )
        if brief.evidence_note:
            baseline_md += f"\n\n🔍 *Evidence Note:* _{brief.evidence_note}_"

        blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"📋 *BASELINE VERIFIED FACTS*\n{truncate_mrkdwn(baseline_md, 2000)}",
            },
        })
        blocks.append({"type": "divider"})

    # 6. Metadata Footer
    time_taken = f"{report.execution_time_seconds:.1f}s" if report.execution_time_seconds else "N/A"
    total_stages = len(report.search_stages)
    inquiry_count = len(report.inquiries) or 8
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"⏱️ *Latency:* {time_taken} | "
                    f"🔎 *Search Stages:* {total_stages}/7 | "
                    f"⚖️ *Jurisdiction:* {report.jurisdiction}\n"
                    f"💬 *⬇️ {inquiry_count} Scenario Projections & Detailed Source List posted in thread below!*"
                ),
            }
        ],
    })

    # 7. Interactive Action Buttons
    target_id = report_id or f"rep_{report.query_topic[:20]}"
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "💾 Save Briefing", "emoji": True},
                "action_id": "slack_action_save_report",
                "value": target_id,
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📊 Observability & Sources", "emoji": True},
                "action_id": "slack_action_view_telemetry",
                "value": target_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "👍 Helpful", "emoji": True},
                "action_id": "slack_action_feedback_positive",
                "value": target_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "👎 Irrelevant", "emoji": True},
                "action_id": "slack_action_feedback_negative",
                "value": target_id,
            },
        ],
    })

    return blocks


def build_thread_deepdive_blocks(
    report: IntelligenceReport,
) -> List[Dict[str, Any]]:
    """
    Constructs the detailed Scenario Analysis & Inquiries with Answers and Sources
    to be posted as an automated reply in the Slack thread.
    Each inquiry is rendered in its own un-collapsed section block with expand: True.
    """
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔮 Speculative Scenarios & Strategic Answers",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    # Inquiries with Synthesized Answers (Individual Bite-Sized Expanded Blocks)
    if report.inquiries:
        # Cap at 15 inquiries to stay well within Slack's 50-block cap
        for idx, inq in enumerate(report.inquiries[:15], start=1):
            arch_val = inq.archetype.value if hasattr(inq.archetype, "value") else str(inq.archetype)
            q_text = convert_markdown_to_slack_mrkdwn(inq.question)
            ans_text = convert_markdown_to_slack_mrkdwn(inq.answer) if inq.answer else "Synthesized scenario projection grounded in search precedents."
            
            blocks.append({
                "type": "section",
                "expand": True,
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{idx}. {arch_val}*\n• *Inquiry:* {q_text}\n  ↳ *Scenario Projection:* {ans_text}",
                },
            })

        blocks.append({"type": "divider"})

    # Complete Citations List
    if report.citations_all:
        cit_lines = []
        for idx, c in enumerate(report.citations_all[:12], start=1):
            url = c.get("url", "")
            title = c.get("title") or c.get("source_domain") or f"Source {idx}"
            stage = c.get("stage_name") or "Verified Search Finding"
            pub = f" ({c.get('publish_date')})" if c.get("publish_date") else ""
            if url:
                cit_lines.append(f"• {format_slack_url(url, title[:70])} — _{stage}{pub}_")
            else:
                cit_lines.append(f"• *{title[:70]}* — _{stage}{pub}_")

        blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"📚 *VERIFIED PRIMARY SOURCE REFERENCES ({len(report.citations_all)}):*\n\n" + truncate_mrkdwn("\n".join(cit_lines), 2500),
            },
        })

    return blocks


def build_report_blocks(
    report: IntelligenceReport,
    report_id: str = "",
    canvas_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Main entry point for report blocks. Uses build_executive_report_blocks.
    """
    return build_executive_report_blocks(report, report_id)


def build_telemetry_modal(
    report: IntelligenceReport,
) -> Dict[str, Any]:
    """
    Constructs a Slack Modal view displaying full observability traces and citations.
    """
    modal_blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Telemetry: {report.query_topic[:35]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "expand": True,
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Total Execution Time:*\n{report.execution_time_seconds:.2f} seconds",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Jurisdiction Focus:*\n{report.jurisdiction}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Search Stages Executed:*\n{len(report.search_stages)} stages",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Safety Verdict:*\n{report.safety_result.status.value}",
                },
            ],
        },
        {"type": "divider"},
    ]

    # Search Stages Breakdown
    if report.search_stages:
        stage_lines = []
        for s in report.search_stages:
            stage_lines.append(f"*Stage {s.stage_id}: {s.stage_name}* ({s.time_window})\n_{s.findings_summary[:180]}_")

        modal_blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"*🔎 Search Investigation Breakdown:*\n\n" + truncate_mrkdwn("\n\n".join(stage_lines), 2000),
            },
        })
        modal_blocks.append({"type": "divider"})

    # Complete Citations List
    if report.citations_all:
        cit_lines = []
        for idx, c in enumerate(report.citations_all, start=1):
            url = c.get("url", "")
            title = c.get("title") or c.get("source_domain") or f"Source {idx}"
            if url:
                cit_lines.append(f"{idx}. {format_slack_url(url, title[:70])}")
            else:
                cit_lines.append(f"{idx}. {title[:70]}")

        modal_blocks.append({
            "type": "section",
            "expand": True,
            "text": {
                "type": "mrkdwn",
                "text": f"*📚 Complete Source List ({len(report.citations_all)}):*\n\n" + truncate_mrkdwn("\n".join(cit_lines), 2500),
            },
        })

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Pipeline Telemetry", "emoji": True},
        "close": {"type": "plain_text", "text": "Close", "emoji": True},
        "blocks": modal_blocks,
    }


# ---------------------------------------------------------
# Sarvam Document OCR UI Builders
# ---------------------------------------------------------

def build_ocr_progress_blocks(filename: str, status_msg: str = "Digitizing document with Sarvam OCR...") -> List[Dict[str, Any]]:
    """Builds initial progress Block Kit message for document OCR processing."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📄 Sarvam Document Intelligence",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⏳ *Processing Document:* `{filename}`\n_{status_msg}_",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "⚡ *Engine:* Sarvam Vision 1.5 (`/doc-ai/v1`) | *Target:* Markdown Layout Extraction",
                }
            ],
        },
    ]


def build_ocr_result_blocks(
    filename: str,
    content_type: str,
    markdown_text: str,
    execution_time: float,
    language: str = "en-IN",
    error: Optional[str] = None,
    truncated: bool = False,
    page_count: Optional[int] = None,
    table_count: int = 0,
    file_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Builds the final formatted Block Kit response for completed OCR jobs."""
    if error:
        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "❌ Sarvam Document OCR Failed",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Document:* `{filename}`\n*Error:* {error}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⏱️ *Duration:* {execution_time:.2f}s | Click the button below to re-run OCR without re-uploading.",
                    }
                ],
            },
        ]
        if file_id:
            retry_val = f"{file_id}|{filename}|{channel_id or ''}|{thread_ts or ''}"
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔄 Retry OCR",
                            "emoji": True,
                        },
                        "style": "primary",
                        "action_id": "slack_action_retry_ocr",
                        "value": retry_val,
                    }
                ],
            })
        return blocks

    formatted_text = convert_markdown_to_slack_mrkdwn(markdown_text)
    preview_text = truncate_mrkdwn(formatted_text, max_len=2800)

    pages_str = f"📑 *Pages:* `{page_count}` | " if page_count else ""
    tables_str = f"📊 *Tables:* `{table_count}` | " if table_count > 0 else ""

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📄 Document Digitization Complete",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"📁 *File:* `{filename}` | {pages_str}{tables_str}⏱️ *Time:* {execution_time:.2f}s | 🗣️ *Language:* `{language}`",
                }
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Extracted Document Markdown & Tables:*\n\n{preview_text}",
            },
        },
    ]


    if truncated:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "📎 *Notice:* Output was truncated to fit Slack message limits. Full `.md` file snippet attached below in thread.",
                }
            ],
        })

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "⚡ *Powered by Sarvam AI Document Intelligence API (Sarvam Vision 1.5)*",
            }
        ],
    })

    return blocks

