"""
Unit tests for Sarvam AI Document Intelligence (OCR) Client, Parser, and OCR Agent.
"""

import unittest
import httpx
from tools.sarvam_client import SarvamOCRClient, SarvamOCRError
from tools.sarvam_parser import convert_html_table_to_markdown, parse_sarvam_output_to_markdown, save_ocr_artifacts
from agents.ocr_agent import execute_sarvam_ocr_job
from schemas.models import OCRProcessingResult


class TestSarvamOCR(unittest.IsolatedAsyncioTestCase):

    def test_mime_type_inference(self):
        self.assertEqual(SarvamOCRClient.infer_mime_type("report.pdf"), "application/pdf")
        self.assertEqual(SarvamOCRClient.infer_mime_type("invoice.png"), "image/png")
        self.assertEqual(SarvamOCRClient.infer_mime_type("scan.jpg"), "image/jpeg")
        self.assertEqual(SarvamOCRClient.infer_mime_type("photo.jpeg"), "image/jpeg")
        self.assertEqual(SarvamOCRClient.infer_mime_type("doc.webp"), "image/webp")
        self.assertEqual(SarvamOCRClient.infer_mime_type("unknown_file"), "application/pdf")

    def test_missing_api_key_raises(self):
        client = SarvamOCRClient(api_key="")
        with self.assertRaises(SarvamOCRError):
            client._get_headers()

    def test_convert_html_table_to_markdown(self):
        sample_html = (
            "<table>"
            "<thead><tr><th>Service</th><th>Charge</th></tr></thead>"
            "<tbody><tr><td>Wireless</td><td>$101.63</td></tr></tbody>"
            "</table>"
        )
        md_table = convert_html_table_to_markdown(sample_html)
        self.assertIn("| Service | Charge |", md_table)
        self.assertIn("| Wireless | $101.63 |", md_table)

    def test_parse_sarvam_ast_output(self):
        mock_ast = {
            "job_id": "job_att_123",
            "type": "digitise",
            "status": "completed",
            "documents": [
                {
                    "filename": "ATTBill_9917.pdf",
                    "pages": [
                        {
                            "page_num": 1,
                            "blocks": [
                                {"layout_tag": "header", "text": "AT&T Mobility Bill", "reading_order": 1},
                                {
                                    "layout_tag": "table",
                                    "text": "<table><tr><th>Account</th><th>Total</th></tr><tr><td>436187939917</td><td>$101.63</td></tr></table>",
                                    "reading_order": 2,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        md_output, meta = parse_sarvam_output_to_markdown(mock_ast)
        self.assertIn("AT&T Mobility Bill", md_output)
        self.assertIn("| 436187939917 | $101.63 |", md_output)
        self.assertEqual(meta["total_pages"], 1)
        self.assertEqual(meta["table_count"], 1)

    async def test_sarvam_ocr_workflow_mock(self):
        """
        Tests the full Sarvam OCR workflow: start_digitise -> poll -> get_results -> parse
        """
        client = SarvamOCRClient(api_key="mock-sarvam-key")

        async def mock_post(self_client, url, *args, **kwargs):
            url_str = str(url)
            if "job/digitise" in url_str:
                return httpx.Response(
                    200,
                    json={"job_id": "job_456"},
                    request=httpx.Request("POST", url_str),
                )
            return httpx.Response(404, request=httpx.Request("POST", url_str))

        async def mock_get(self_client, url, *args, **kwargs):
            url_str = str(url)
            if "status" in url_str:
                return httpx.Response(
                    200,
                    json={"job_id": "job_456", "status": "completed"},
                    request=httpx.Request("GET", url_str),
                )
            elif "results" in url_str:
                return httpx.Response(
                    200,
                    json={
                        "job_id": "job_456",
                        "documents": [
                            {
                                "filename": "test_report.pdf",
                                "pages": [
                                    {
                                        "page_num": 1,
                                        "blocks": [
                                            {
                                                "layout_tag": "header",
                                                "text": "Annual Financial Report 2026",
                                                "reading_order": 1,
                                            },
                                            {
                                                "layout_tag": "paragraph",
                                                "text": "Total Revenue: INR 4500 Cr.",
                                                "reading_order": 2,
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                    request=httpx.Request("GET", url_str),
                )
            return httpx.Response(404, request=httpx.Request("GET", url_str))

        original_post = httpx.AsyncClient.post
        original_get = httpx.AsyncClient.get

        httpx.AsyncClient.post = mock_post
        httpx.AsyncClient.get = mock_get

        try:
            result_md, meta, json_path, md_path = await client.digitize_document(
                file_bytes=b"%PDF-1.4 mock pdf data",
                filename="test_report.pdf",
            )
            self.assertIn("Annual Financial Report 2026", result_md)
            self.assertIn("INR 4500 Cr", result_md)
            self.assertEqual(meta["total_pages"], 1)
        finally:
            httpx.AsyncClient.post = original_post
            httpx.AsyncClient.get = original_get

    async def test_execute_sarvam_ocr_job(self):
        """
        Tests execute_sarvam_ocr_job wrapper.
        """
        original_digitize = SarvamOCRClient.digitize_document

        async def mock_digitize(*args, **kwargs):
            return (
                "## Extracted Bill of Lading\n- Container: MSKU123456\n- Weight: 24,000 kg",
                {"total_pages": 1, "table_count": 1},
                "/tmp/ocr.json",
                "/tmp/ocr.md",
            )

        SarvamOCRClient.digitize_document = mock_digitize
        try:
            result: OCRProcessingResult = await execute_sarvam_ocr_job(
                file_bytes=b"dummy",
                filename="custom_doc.pdf",
                api_key="mock_key",
            )

            self.assertIsNone(result.error)
            self.assertIn("Extracted Bill of Lading", result.markdown_content)
            self.assertEqual(result.filename, "custom_doc.pdf")
            self.assertEqual(result.content_type, "application/pdf")
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.table_count, 1)
        finally:
            SarvamOCRClient.digitize_document = original_digitize


if __name__ == "__main__":
    unittest.main()
