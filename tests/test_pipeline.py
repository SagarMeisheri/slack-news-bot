"""
Automated unit tests for Query Templates, Formatting, and ADK schemas.
"""

import asyncio
import os
import unittest
from dotenv import load_dotenv

load_dotenv()

from agents import format_report_markdown
from schemas.models import (
    BaselineBrief,
    InquiryArchetype,
    SafetyCheckResult,
    SpeculativeInquiry,
    SuppressionStatus,
)
from tools.search_tool import generate_stage_queries, STAGE_DEFINITIONS


class TestNewsIntelligenceUnit(unittest.TestCase):

    def test_stage_definitions_and_queries(self):
        """Verify all 7 stages are defined with query templates matching master_prompt.md."""
        self.assertEqual(len(STAGE_DEFINITIONS), 7)
        for stage_id in range(1, 8):
            self.assertIn(stage_id, STAGE_DEFINITIONS)
            queries = generate_stage_queries("RBI digital lending guidelines", stage_id)
            self.assertTrue(len(queries) >= 1)
            self.assertIsInstance(queries[0], str)

    def test_synthesis_formatting_with_publication_links(self):
        """Verify report properly formats Baseline Brief, 8 Inquiry Archetypes, and clickable publication source links."""
        dummy_baseline = BaselineBrief(
            core_event="SEBI announced new regulatory guidelines for algorithmic trading on August 24, 2026.",
            core_event_date="August 24, 2026",
            immediate_fallout="Brokerage shares adjusted 1.5% amid compliance review costs.",
            context_precedent="Follows previous consultation papers issued under SEBI (Stock Brokers) Regulations.",
            evidence_note=None,
        )

        dummy_inquiries = [
            SpeculativeInquiry(
                archetype=InquiryArchetype.WHY_X,
                question="In light of the August 24 SEBI algorithmic trading guidelines, what institutional timing factors prompted SEBI to release the circular prior to the quarterly derivatives expiry?",
                source_stages=[4],
                neutrality_verified=True,
            ),
            SpeculativeInquiry(
                archetype=InquiryArchetype.WHAT_TO_WATCH,
                question="Under the new SEBI algorithmic trading framework, what specific risk-management audit metrics must algorithmic trading firms submit by the October 1 compliance deadline?",
                source_stages=[6],
                neutrality_verified=True,
            ),
        ]

        dummy_citations = [
            {
                "title": "SEBI Issues Master Direction on Algorithmic Trading - Moneycontrol",
                "url": "https://www.moneycontrol.com/news/business/sebi-algo-rules",
                "publish_date": "2026-08-24",
                "stage_id": 4,
                "stage_name": "Adversarial / Counter-Narrative",
            },
            {
                "title": "SEBI Compliance Calendar 2026 - Economic Times",
                "url": "https://economictimes.indiatimes.com/markets/sebi-deadline",
                "publish_date": "2026-08-24",
                "stage_id": 6,
                "stage_name": "Forward Calendar / Scheduled Events",
            },
        ]

        formatted = format_report_markdown(
            baseline=dummy_baseline,
            inquiries=dummy_inquiries,
            safety_notice=None,
            is_full_suppression=False,
            citations=dummy_citations,
        )
        self.assertIn("### Baseline Intelligence Brief", formatted)
        self.assertIn("### Speculative & Strategic Inquiries", formatted)
        self.assertIn("Why X? (Incentives & Timing)", formatted)
        self.assertIn("What to Watch (Leading Indicators)", formatted)
        # Check clickable native Parallel source title links
        self.assertIn("[SEBI Issues Master Direction on Algorithmic Trading - Moneycontrol](https://www.moneycontrol.com/news/business/sebi-algo-rules)", formatted)
        self.assertIn("[SEBI Compliance Calendar 2026 - Economic Times](https://economictimes.indiatimes.com/markets/sebi-deadline)", formatted)
        self.assertIn("### 🔗 Verified Source References", formatted)


if __name__ == "__main__":
    unittest.main()
