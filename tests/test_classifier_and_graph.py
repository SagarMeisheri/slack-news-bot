"""
Unit tests for ADK Intent Classifier and Request Routing.
"""

import unittest
from agents.classifier_agent import classify_incoming_request
from schemas.models import RequestIntent


class TestClassifierAndRouting(unittest.IsolatedAsyncioTestCase):

    async def test_classifier_file_attachment_routing(self):
        res = await classify_incoming_request(
            text="Please check this file",
            has_files=True,
            file_names=["quarterly_results.pdf"],
        )
        self.assertEqual(res.intent, RequestIntent.DOCUMENT_OCR)
        self.assertEqual(res.confidence, 1.0)

    async def test_classifier_ocr_keyword_routing(self):
        queries = [
            "Can you perform OCR on this receipt?",
            "Please digitize the document",
            "Extract text from this image",
            "Run sarvam ocr on this scan",
        ]
        for q in queries:
            res = await classify_incoming_request(text=q, has_files=False)
            self.assertEqual(res.intent, RequestIntent.DOCUMENT_OCR, f"Failed for query: {q}")

    async def test_classifier_news_intelligence_routing(self):
        queries = [
            "RBI liquidity infusion impact on banking sector equities",
            "TSMC tariff impact on semiconductor supply chain",
            "Adani port expansion environmental clearance status",
            "What is the outlook on Brent crude futures following OPEC meeting?",
        ]
        for q in queries:
            res = await classify_incoming_request(text=q, has_files=False)
            self.assertEqual(res.intent, RequestIntent.NEWS_INTELLIGENCE, f"Failed for query: {q}")


if __name__ == "__main__":
    unittest.main()
