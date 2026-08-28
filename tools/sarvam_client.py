"""
Sarvam AI Document Intelligence (OCR) Client.
Provides asynchronous document digitization (PDF, PNG, JPG) using Sarvam Vision 1.5.
Docs: https://docs.sarvam.ai/
"""

import asyncio
import logging
import mimetypes
from typing import Any, Dict, List, Optional, Tuple
import httpx


from config import get_sarvam_api_key, get_sarvam_default_language

logger = logging.getLogger("sarvam_client")

SARVAM_BASE_URL = "https://api.sarvam.ai/doc-ai/v1"


class SarvamOCRError(Exception):
    """Custom exception raised for Sarvam OCR API failures."""
    pass


class SarvamOCRClient:
    """
    Asynchronous client for Sarvam Document Intelligence API (/doc-ai/v1).
    Performs multipart/form-data job submission, status polling, and markdown extraction.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = SARVAM_BASE_URL,
        timeout: float = 60.0,
    ):
        self.api_key = api_key if api_key is not None else get_sarvam_api_key()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self, is_json: bool = True) -> Dict[str, str]:
        if not self.api_key or self.api_key in ("your_sarvam_api_key", "mock_placeholder"):
            raise SarvamOCRError("SARVAM_API_KEY is not configured. Please set it in your environment or .env file.")
        headers = {"api-subscription-key": self.api_key}
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def infer_mime_type(filename: str, default: str = "application/pdf") -> str:
        """Infers MIME content type from filename extension."""
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            ext = filename.lower().split(".")[-1] if "." in filename else ""
            if ext in ("pdf",):
                return "application/pdf"
            elif ext in ("png",):
                return "image/png"
            elif ext in ("jpg", "jpeg"):
                return "image/jpeg"
            elif ext in ("webp",):
                return "image/webp"
            return default
        return mime_type

    async def create_upload_slot(self, content_type: str) -> Dict[str, Any]:
        """
        Requests a presigned upload URL and upload_id from Sarvam.
        POST /doc-ai/v1/job/upload
        """
        headers = self._get_headers(is_json=True)
        url = f"{self.base_url}/job/upload"
        payload = {"content_type": content_type}

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code not in (200, 201, 202):
                logger.error(f"Sarvam upload slot creation failed: {resp.status_code} - {resp.text}")
                raise SarvamOCRError(f"Failed to create upload slot: {resp.status_code} - {resp.text}")
            return resp.json()

    async def upload_document_bytes(
        self,
        upload_data: Dict[str, Any],
        file_bytes: bytes,
        content_type: str,
    ) -> str:
        """
        Uploads the raw binary bytes to the presigned upload URL or storage target.
        Returns the upload_id.
        """
        upload_id = upload_data.get("upload_id") or upload_data.get("id")
        upload_url = upload_data.get("url") or upload_data.get("upload_url")

        if not upload_id:
            raise SarvamOCRError(f"No upload_id returned from Sarvam upload slot: {upload_data}")

        if not upload_url:
            return str(upload_id)

        # Upload binary to presigned URL (typically PUT with Azure/S3 headers)
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            upload_headers = {"Content-Type": content_type}
            if "headers" in upload_data and isinstance(upload_data["headers"], dict):
                upload_headers.update(upload_data["headers"])

            resp = await client.put(upload_url, headers=upload_headers, content=file_bytes)
            if resp.status_code not in (200, 201, 202, 204):
                if resp.status_code == 405:
                    resp = await client.post(upload_url, headers=upload_headers, content=file_bytes)
                
                if resp.status_code not in (200, 201, 202, 204):
                    logger.error(f"Failed to upload document binary to presigned URL: {resp.status_code} - {resp.text}")
                    raise SarvamOCRError(f"Binary upload failed: {resp.status_code} - {resp.text}")

        return str(upload_id)

    async def start_digitise_job(
        self,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        upload_id: Optional[str] = None,
        language: Optional[str] = None,
        output_format: str = "md",
    ) -> str:
        """
        Initiates an asynchronous OCR digitization job via multipart/form-data.
        POST /doc-ai/v1/job/digitise
        Supports both direct binary file upload and pre-uploaded upload_ids.
        Returns job_id.
        """
        headers = self._get_headers(is_json=False)
        url = f"{self.base_url}/job/digitise"
        lang = language or get_sarvam_default_language()

        data: Dict[str, Any] = {
            "language": lang,
            "output_format": output_format,
        }

        files = None
        if file_bytes is not None:
            fn = filename or "document.pdf"
            ct = content_type or self.infer_mime_type(fn)
            files = [("file", (fn, file_bytes, ct))]
        elif upload_id:
            data["upload_ids"] = str(upload_id)
        else:
            raise SarvamOCRError("Either file_bytes or upload_id must be provided to start_digitise_job.")

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            if resp.status_code not in (200, 201, 202):
                logger.error(f"Sarvam start digitise job failed: {resp.status_code} - {resp.text}")
                raise SarvamOCRError(f"Failed to start digitise job: {resp.status_code} - {resp.text}")
            
            resp_data = resp.json()
            job_id = resp_data.get("job_id") or resp_data.get("id")
            if not job_id:
                raise SarvamOCRError(f"No job_id found in digitise response: {resp_data}")
            return str(job_id)

    async def poll_job_status(
        self,
        job_id: str,
        max_wait_seconds: int = 120,
        poll_interval: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Polls the job status until it reaches 'completed', 'failed', or timeout.
        GET /doc-ai/v1/job/{job_id}/status
        """
        headers = self._get_headers(is_json=True)
        url = f"{self.base_url}/job/{job_id}/status"
        elapsed = 0.0

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            while elapsed < max_wait_seconds:
                resp = await client.get(url, headers=headers)
                if resp.status_code not in (200, 201, 202):
                    logger.warning(f"Poll job status returned {resp.status_code}: {resp.text}")
                else:
                    data = resp.json()
                    status = str(data.get("status", "")).lower()
                    if status in ("completed", "success", "done"):
                        return data
                    elif status in ("failed", "error"):
                        err_msg = data.get("error") or data.get("message") or "Unknown Sarvam OCR processing error"
                        raise SarvamOCRError(f"Sarvam OCR job failed: {err_msg}")
                
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise SarvamOCRError(f"Sarvam OCR job timed out after {max_wait_seconds} seconds (job_id={job_id})")

    async def get_job_results(self, job_id: str, filename: str = "document.pdf") -> Tuple[str, Dict[str, Any], Optional[str], Optional[str]]:
        """
        Fetches completed output from results endpoint, parses HTML tables & AST into Markdown,
        and saves raw JSON and Markdown artifacts to disk.
        
        Returns:
            (formatted_markdown, doc_metadata, json_path, md_path)
        """
        from tools.sarvam_parser import parse_sarvam_output_to_markdown, save_ocr_artifacts

        headers = self._get_headers(is_json=True)
        url = f"{self.base_url}/job/{job_id}/results"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code not in (200, 201, 202):
                logger.error(f"Failed to fetch job results for {job_id}: {resp.status_code} - {resp.text}")
                raise SarvamOCRError(f"Failed to fetch job results: {resp.status_code} - {resp.text}")
            
            raw_data = resp.json()

        # Parse AST, HTML tables, and layout tags into Markdown
        markdown_text, metadata = parse_sarvam_output_to_markdown(raw_data)
        
        # Save artifacts to disk
        json_path, md_path = save_ocr_artifacts(
            raw_data=raw_data,
            markdown_content=markdown_text,
            filename=filename,
        )

        return markdown_text, metadata, json_path, md_path

    async def digitize_document(
        self,
        file_bytes: bytes,
        filename: str = "document.pdf",
        content_type: Optional[str] = None,
        language: Optional[str] = None,
        max_wait_seconds: int = 120,
    ) -> Tuple[str, Dict[str, Any], Optional[str], Optional[str]]:
        """
        High-level helper: launches digitise job via multipart/form-data, polls until completion,
        parses HTML tables & AST into Markdown, saves artifacts, and returns:
        (markdown_text, doc_metadata, json_path, md_path)
        """
        ct = content_type or self.infer_mime_type(filename)
        logger.info(f"Initiating Sarvam OCR digitization for {filename} (MIME: {ct})")

        # 1. Start digitise job directly via multipart/form-data
        job_id = await self.start_digitise_job(
            file_bytes=file_bytes,
            filename=filename,
            content_type=ct,
            language=language,
            output_format="md",
        )
        logger.info(f"Sarvam digitise job started with ID: {job_id}")

        # 2. Poll status until completion
        await self.poll_job_status(job_id=job_id, max_wait_seconds=max_wait_seconds)

        # 3. Retrieve, parse, and save results
        markdown_text, metadata, json_path, md_path = await self.get_job_results(job_id=job_id, filename=filename)
        logger.info(
            f"Sarvam OCR completed for {filename} (Pages: {metadata.get('total_pages')}, "
            f"Tables: {metadata.get('table_count')}, Length: {len(markdown_text)} chars)"
        )
        return markdown_text, metadata, json_path, md_path

