"""
ADK-compatible Sarvam Document OCR Execution Agent.
Coordinates document digitization via Sarvam Document Intelligence API
and prepares Slack Block Kit and Markdown outputs.
"""

import logging
import time
from typing import Optional
from schemas.models import OCRProcessingResult
from tools.sarvam_client import SarvamOCRClient, SarvamOCRError

logger = logging.getLogger("ocr_agent")

MAX_SLACK_TEXT_LENGTH = 3000


async def execute_sarvam_ocr_job(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    language: Optional[str] = None,
    api_key: Optional[str] = None,
) -> OCRProcessingResult:
    """
    Executes the complete Sarvam OCR pipeline for an uploaded document/image.
    """
    start_time = time.time()
    client = SarvamOCRClient(api_key=api_key)
    ct = content_type or client.infer_mime_type(filename)

    try:
        markdown_output, metadata, json_path, md_path = await client.digitize_document(
            file_bytes=file_bytes,
            filename=filename,
            content_type=ct,
            language=language,
        )
        duration = round(time.time() - start_time, 2)
        
        needs_file_upload = len(markdown_output) > MAX_SLACK_TEXT_LENGTH
        
        return OCRProcessingResult(
            filename=filename,
            content_type=ct,
            markdown_content=markdown_output,
            page_count=metadata.get("total_pages", 1),
            table_count=metadata.get("table_count", 0),
            execution_time_seconds=duration,
            language=language or "en-IN",
            truncated=needs_file_upload,
            file_upload_required=needs_file_upload,
            json_filepath=json_path,
            md_filepath=md_path,
            error=None,
        )

    except SarvamOCRError as e:
        logger.error(f"Sarvam OCR failed for {filename}: {e}")
        duration = round(time.time() - start_time, 2)
        return OCRProcessingResult(
            filename=filename,
            content_type=ct,
            markdown_content="",
            execution_time_seconds=duration,
            error=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error during OCR processing for {filename}: {e}")
        duration = round(time.time() - start_time, 2)
        return OCRProcessingResult(
            filename=filename,
            content_type=ct,
            markdown_content="",
            execution_time_seconds=duration,
            error=f"Internal OCR Error: {str(e)}",
        )
