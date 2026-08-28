"""
Unit tests for the Slack Bolt UI formatter, configuration validation, and event handling logic.
"""

import os
import unittest
from unittest.mock import patch

from config import validate_slack_config
from schemas.models import (
    BaselineBrief,
    IntelligenceReport,
    InquiryArchetype,
    SafetyCategory,
    SafetyCheckResult,
    SearchStageResult,
    SpeculativeInquiry,
    SuppressionStatus,
)
from slack_ui import (
    build_executive_report_blocks,
    build_progress_blocks,
    build_report_blocks,
    build_safety_suppression_blocks,
    build_telemetry_modal,
    build_thread_deepdive_blocks,
    convert_markdown_to_slack_mrkdwn,
    format_as_bullet_points,
    format_slack_url,
    split_markdown_into_slack_blocks,
    truncate_mrkdwn,
)



class TestSlackBotUI(unittest.TestCase):

    def test_validate_slack_config_missing_tokens(self):
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "", "SLACK_APP_TOKEN": ""}):
            is_valid, msg = validate_slack_config()
            self.assertFalse(is_valid)
            self.assertIn("SLACK_BOT_TOKEN is missing", msg)

    def test_validate_slack_config_valid(self):
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test-12345", "SLACK_APP_TOKEN": "xapp-test-67890"}):
            is_valid, msg = validate_slack_config()
            self.assertTrue(is_valid)
            self.assertEqual(msg, "")

    def test_truncate_mrkdwn(self):
        short_text = "Short text"
        self.assertEqual(truncate_mrkdwn(short_text, max_len=50), short_text)

        long_text = "A" * 100
        truncated = truncate_mrkdwn(long_text, max_len=50)
        self.assertLessEqual(len(truncated), 50)
        self.assertIn("_...[truncated]_", truncated)

    def test_format_slack_url(self):
        formatted = format_slack_url("https://example.com/news?a=1&b=2", "Example <Title> & News")
        self.assertEqual(formatted, "<https://example.com/news?a=1&b=2|Example &lt;Title&gt; &amp; News>")

    def test_convert_markdown_to_slack_mrkdwn(self):
        md = "### Core Brief\nCheck [Reuters](https://reuters.com/article) for **major updates**."
        mrkdwn = convert_markdown_to_slack_mrkdwn(md)
        self.assertIn("<https://reuters.com/article|Reuters>", mrkdwn)
        self.assertIn("*major updates*", mrkdwn)
        self.assertIn("*Core Brief*", mrkdwn)

    def test_format_as_bullet_points(self):
        prose = "TSMC began tool installation. Production begins in Q1 2026. Global supply chains will stabilize."
        bullets = format_as_bullet_points(prose)
        self.assertIn("• TSMC began tool installation.", bullets)
        self.assertIn("• Production begins in Q1 2026.", bullets)
        self.assertIn("• Global supply chains will stabilize.", bullets)

        existing_bullets = "* Item 1\n- Item 2\n• Item 3"
        normalized = format_as_bullet_points(existing_bullets)
        self.assertEqual(normalized, "• Item 1\n• Item 2\n• Item 3")


    def test_split_markdown_into_slack_blocks(self):
        text = "Section 1\n\n---\n\nSection 2 with [Link](https://example.com)"
        mrkdwn = convert_markdown_to_slack_mrkdwn(text)
        blocks = split_markdown_into_slack_blocks(mrkdwn, max_chunk_len=500)
        self.assertIsInstance(blocks, list)
        self.assertTrue(any(b["type"] == "divider" for b in blocks))
        self.assertTrue(any(b["type"] == "section" for b in blocks))

    def test_build_progress_blocks(self):
        statuses = {
            "safety": "completed",
            "breaking": "running",
            "precedent": "pending",
            "social": "pending",
            "calendar": "pending",
            "synthesis": "pending",
        }
        blocks = build_progress_blocks(
            topic="Semiconductor Tariff Impact",
            statuses=statuses,
            current_detail="Querying Parallel search API...",
        )
        self.assertIsInstance(blocks, list)
        self.assertGreaterEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["type"], "header")
        self.assertIn("ADK News Intelligence Pipeline", blocks[0]["text"]["text"])

        section_text = blocks[1]["text"]["text"]
        self.assertIn("Semiconductor Tariff Impact", section_text)
        self.assertIn("✅ *Safety & Compliance Triage*", section_text)
        self.assertIn("⏳ *Breaking & Fallout Search*", section_text)
        self.assertIn("Public Sentiment & Social Media Buzz", section_text)

        self.assertIn("Querying Parallel search API", section_text)

    def test_build_safety_suppression_blocks(self):
        safety_result = SafetyCheckResult(
            status=SuppressionStatus.FULL_SUPPRESSION,
            categories_triggered=[SafetyCategory.ACTIVE_EMERGENCY, SafetyCategory.MICRO_CAP_RUMORS],
            rationale="Active disaster rescue operation underway; speculative coverage suppressed.",
        )
        blocks = build_safety_suppression_blocks(topic="Emergency Event", safety_result=safety_result)
        self.assertIsInstance(blocks, list)
        self.assertEqual(blocks[0]["type"], "header")
        self.assertIn("Suppressed", blocks[0]["text"]["text"])
        self.assertIn("Active Emergencies", blocks[1]["text"]["text"])

    def test_build_report_blocks(self):
        report = IntelligenceReport(
            query_topic="TSMC 2nm Fab Expansion",
            jurisdiction="Global / Taiwan",
            executive_summary="TSMC is accelerating 2nm wafer fabrication ahead of schedule.",
            safety_result=SafetyCheckResult(status=SuppressionStatus.NO_SUPPRESSION),
            search_stages=[
                SearchStageResult(
                    stage_id=1,
                    stage_name="Breaking Ground Truth",
                    time_window="Strict: 0-7 days",
                    objective="Ground truth verification",
                    findings_summary="TSMC broke ground on new Kaohsiung facility.",
                    citations=[{"url": "https://reuters.com/tsmc", "title": "Reuters TSMC"}],
                )
            ],
            baseline_brief=BaselineBrief(
                core_event="TSMC officially commenced construction on Kaohsiung 2nm wafer plant.",
                core_event_date="August 24, 2026",
                immediate_fallout="ASML and supplier shares rose 2.4% following the announcement.",
                context_precedent="Follows the 2024 Arizona foundry delays.",
            ),
            inquiries=[
                SpeculativeInquiry(
                    archetype=InquiryArchetype.WHAT_IT_MEANS,
                    question="Will packaging bottlenecks constrain output before 2027?",
                    answer="Advanced packaging lines at Kaohsiung are expected to mitigate CoWoS bottlenecks by mid-2027.",
                    source_stages=[1, 2],
                    grounding_anchor="CoWoS capacity",
                )
            ],
            formatted_markdown="### Executive Summary\nTSMC 2nm acceleration.\n\n### Scenarios\n* **Inquiry**: Will packaging bottlenecks constrain output?\n  **Projection**: Packaging capacity is expanding [Reuters](https://reuters.com/tsmc).",
            citations_all=[{"url": "https://reuters.com/tsmc", "title": "Reuters TSMC"}],
            execution_time_seconds=14.2,
        )

        report.top_headlines = ["[TSMC begins mass tool installation](https://reuters.com/tsmc) — Reuters (2026-08-24)"]

        # 1. Test Executive Blocks (Main message)
        exec_blocks = build_executive_report_blocks(report, report_id="rep_test_12345")
        self.assertIsInstance(exec_blocks, list)
        self.assertGreaterEqual(len(exec_blocks), 4)
        self.assertEqual(exec_blocks[0]["type"], "header")
        self.assertIn("TSMC 2nm Fab Expansion", exec_blocks[0]["text"]["text"])

        exec_combined = "\n".join([b["text"]["text"] for b in exec_blocks if b.get("text") and isinstance(b["text"], dict)])
        self.assertIn("TSMC is accelerating 2nm wafer fabrication", exec_combined)
        self.assertIn("TOP BREAKING HEADLINES", exec_combined)
        self.assertIn("BASELINE VERIFIED FACTS", exec_combined)

        # 2. Test Thread Deep-Dive Blocks
        thread_blocks = build_thread_deepdive_blocks(report)
        self.assertIsInstance(thread_blocks, list)
        self.assertGreaterEqual(len(thread_blocks), 3)
        self.assertEqual(thread_blocks[0]["type"], "header")
        self.assertIn("Speculative Scenarios", thread_blocks[0]["text"]["text"])

        thread_combined = "\n".join([b["text"]["text"] for b in thread_blocks if b.get("text") and isinstance(b["text"], dict)])
        self.assertIn("Will packaging bottlenecks constrain output", thread_combined)
        self.assertIn("Advanced packaging lines at Kaohsiung", thread_combined)
        self.assertIn("VERIFIED PRIMARY SOURCE REFERENCES", thread_combined)

    def test_build_telemetry_modal(self):
        report = IntelligenceReport(
            query_topic="Adani Green Energy Expansion",
            jurisdiction="India",
            safety_result=SafetyCheckResult(status=SuppressionStatus.NO_SUPPRESSION),
            search_stages=[
                SearchStageResult(
                    stage_id=1,
                    stage_name="Breaking Ground Truth",
                    time_window="Strict: 0-7 days",
                    objective="Primary facts",
                    findings_summary="Commissioned 2GW solar plant in Khavda.",
                )
            ],
            citations_all=[{"url": "https://adani.com/solar", "title": "Official Announcement"}],
            execution_time_seconds=11.5,
        )
        modal = build_telemetry_modal(report)
        self.assertEqual(modal["type"], "modal")
        self.assertIn("Pipeline Telemetry", modal["title"]["text"])
        self.assertGreaterEqual(len(modal["blocks"]), 3)


if __name__ == "__main__":
    unittest.main()
