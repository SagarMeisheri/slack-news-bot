"""
Slack UI Block Kit Formatter for ADK News Intelligence.
Generates dynamic progress indicators, rich structured briefing blocks,
adaptive markdown formatting with inline links, interactive action buttons, and telemetry modals.
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


def split_markdown_into_slack_blocks(mrkdwn_text: str, max_chunk_len: int = 2700) -> List[Dict[str, Any]]:
    """
    Splits converted mrkdwn text into structured Slack section blocks,
    respecting Slack's 3,000 character limit per block.
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
                    "text": {"type": "mrkdwn", "text": current_chunk},
                })
                current_chunk = ""
            blocks.append({"type": "divider"})
            continue

        if len(current_chunk) + len(p_str) + 2 > max_chunk_len:
            if current_chunk:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": current_chunk},
                })
                current_chunk = ""

            # If an individual paragraph exceeds max chunk length, split it
            while len(p_str) > max_chunk_len:
                sub_part = p_str[:max_chunk_len]
                blocks.append({
                    "type": "section",
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
            "text": {"type": "mrkdwn", "text": current_chunk},
        })

    return blocks


def build_progress_blocks(
    topic: str,
    statuses: Dict[str, str],
    current_detail: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Constructs a live step-by-step progress view updated via chat_update.
    """
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
    if current_detail:
        progress_text += f"\n\n⚡ *Active Operation:* `{current_detail[:120]}`"

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


def build_report_blocks(
    report: IntelligenceReport,
    report_id: str = "",
) -> List[Dict[str, Any]]:
    """
    Constructs the final rich Block Kit briefing for Slack from the full synthesized markdown,
    incorporating Executive TL;DR, answers with inline citations, verified references, and action buttons.
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
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Editorial Notice (Partial Clearance):* {cats}\n_{report.safety_result.rationale}_",
            },
        })
        blocks.append({"type": "divider"})

    # 3. Render Synthesized Markdown Content
    markdown_content = report.formatted_markdown or ""

    # If formatted_markdown is present, convert and chunk it directly
    if markdown_content:
        converted_mrkdwn = convert_markdown_to_slack_mrkdwn(markdown_content)
        content_blocks = split_markdown_into_slack_blocks(converted_mrkdwn, max_chunk_len=2700)
        # Limit content blocks to prevent hitting Slack's 50 block cap (reserve 5 for header/footer/actions)
        blocks.extend(content_blocks[:42])
    else:
        # Fallback manual reconstruction if formatted_markdown is empty
        if report.executive_summary:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚡ *EXECUTIVE TL;DR*\n\n{truncate_mrkdwn(report.executive_summary, 2700)}",
                },
            })
            blocks.append({"type": "divider"})

        if report.baseline_brief:
            brief = report.baseline_brief
            date_str = f" *[{brief.core_event_date}]*" if brief.core_event_date else ""
            baseline_md = (
                f"📌 *Core Event{date_str}:*\n{brief.core_event}\n\n"
                f"💥 *Immediate Fallout:*\n{brief.immediate_fallout}\n\n"
                f"🏛️ *Context & Precedent:*\n{brief.context_precedent}"
            )
            if brief.evidence_note:
                baseline_md += f"\n\n🔍 *Evidence Note:* _{brief.evidence_note}_"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📋 *BASELINE VERIFIED FACTS*\n\n{truncate_mrkdwn(baseline_md, 2700)}",
                },
            })
            blocks.append({"type": "divider"})

        if report.inquiries:
            inquiry_lines = []
            for idx, inq in enumerate(report.inquiries[:10], start=1):
                arch_val = inq.archetype.value if hasattr(inq.archetype, "value") else str(inq.archetype)
                ans_str = f"\n  ↳ *Analysis:* {inq.answer}" if inq.answer else ""
                inquiry_lines.append(f"*{idx}. {arch_val}*\n• *Inquiry:* {inq.question}{ans_str}")

            inquiries_md = "\n\n".join(inquiry_lines)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔮 *SCENARIOS & GROUNDED ANSWERS*\n\n{truncate_mrkdwn(inquiries_md, 2700)}",
                },
            })
            blocks.append({"type": "divider"})

        if report.citations_all:
            citation_links = []
            for idx, c in enumerate(report.citations_all[:8], start=1):
                url = c.get("url", "")
                title = c.get("title") or c.get("source_domain") or f"Source {idx}"
                if url:
                    citation_links.append(f"[{idx}] {format_slack_url(url, title[:50])}")
                else:
                    citation_links.append(f"[{idx}] {title[:50]}")

            cit_text = " • ".join(citation_links)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📚 *Primary Sources & Citations:*\n{truncate_mrkdwn(cit_text, 2500)}",
                },
            })

    blocks.append({"type": "divider"})

    # 4. Metadata Footer
    time_taken = f"{report.execution_time_seconds:.1f}s" if report.execution_time_seconds else "N/A"
    total_stages = len(report.search_stages)
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"⏱️ *Latency:* {time_taken} | "
                    f"🔎 *Search Stages:* {total_stages}/7 | "
                    f"⚖️ *Jurisdiction:* {report.jurisdiction} | "
                    f"🤖 *ADK Multi-Agent Pipeline*"
                ),
            }
        ],
    })

    # 5. Interactive Action Buttons
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
