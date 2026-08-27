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
    build_progress_blocks,
    build_report_blocks,
    build_safety_suppression_blocks,
    build_telemetry_modal,
    convert_markdown_to_slack_mrkdwn,
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

        blocks = build_report_blocks(report, report_id="rep_test_12345")
        self.assertIsInstance(blocks, list)
        self.assertGreaterEqual(len(blocks), 4)

        # Verify Header
        self.assertEqual(blocks[0]["type"], "header")
        self.assertIn("TSMC 2nm Fab Expansion", blocks[0]["text"]["text"])

        # Verify Actions Block
        actions_block = [b for b in blocks if b["type"] == "actions"][0]
        action_ids = [el["action_id"] for el in actions_block["elements"]]
        self.assertIn("slack_action_save_report", action_ids)
        self.assertIn("slack_action_view_telemetry", action_ids)
        self.assertIn("slack_action_feedback_positive", action_ids)
        self.assertIn("slack_action_feedback_negative", action_ids)

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
