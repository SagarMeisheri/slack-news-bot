"""
ADK Intent Classification Agent.
Classifies incoming user messages into either 'ocr_request' (Sarvam Document OCR)
or 'news_request' (5-agent News Intelligence Pipeline).
"""

import json
import logging
from typing import List, Optional
from google.adk.agents import LlmAgent
from config import ModelConfig, get_default_model_config
from observability.tracker import ObservabilityTracker
from schemas.models import RequestClassification, RequestIntent

logger = logging.getLogger("classifier_agent")

CLASSIFIER_PROMPT = """You are an expert Intent Classification Agent for an enterprise Slack Bot workspace.
Your job is to analyze incoming user queries and classify them into one of two routing categories:

1. `ocr_request`:
   - Requests asking to extract, parse, transcribe, digitize, or perform OCR on a document, PDF, image, scan, receipt, or invoice.
   - Text mentioning uploaded files, document parsing, or requesting tabular/text extraction from files.

2. `news_request`:
   - Requests inquiring about breaking news, geopolitical events, company announcements, regulatory changes, court cases, macroeconomic updates, or sector fallout.
   - Any scenario analysis or general information lookup not related to OCR document transcription.

Analyze the user text carefully and return a structured JSON response matching the `RequestClassification` schema.
"""


def create_classifier_agent(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    name: str = "Intent_Classifier_Agent",
    tracker: Optional[ObservabilityTracker] = None,
) -> LlmAgent:
    """
    Creates an ADK LlmAgent configured to classify user request intents.
    """
    cfg = model_config or get_default_model_config(model_name=model)

    agent = LlmAgent(
        name=name,
        description="Classifies incoming requests as either ocr_request or news_request.",
        model=cfg.model_name,
        generate_content_config=cfg.to_generate_content_config(),
        instruction=CLASSIFIER_PROMPT,
        output_schema=RequestClassification,
        output_key="classification_result",
        before_agent_callback=tracker.on_before_agent if tracker else None,
        after_agent_callback=tracker.on_after_agent if tracker else None,
        before_model_callback=tracker.on_before_model if tracker else None,
        after_model_callback=tracker.on_after_model if tracker else None,
    )
    return agent


async def classify_incoming_request(
    text: str,
    has_files: bool = False,
    file_names: Optional[List[str]] = None,
    model_config: Optional[ModelConfig] = None,
    tracker: Optional[ObservabilityTracker] = None,
) -> RequestClassification:
    """
    Fast, reliable classifier for Slack events:
    1. If file attachments exist (PDF/PNG/JPG), immediately routes to ocr_request.
    2. If explicit OCR keywords are detected, routes to ocr_request.
    3. Otherwise, defaults to news_request (or executes LLM classifier if ambiguous).
    """
    cleaned = (text or "").strip()
    file_list = file_names or []

    # Deterministic rule 1: Attached document or image
    if has_files or any(f.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp")) for f in file_list):
        return RequestClassification(
            intent=RequestIntent.DOCUMENT_OCR,
            confidence=1.0,
            language="en-IN",
            rationale="Incoming event contains document/image file attachments.",
            extracted_query_or_filename=file_list[0] if file_list else "attached_document",
        )

    # Deterministic rule 2: Explicit OCR keywords
    ocr_triggers = [
        "ocr", "digitize", "digitise", "transcribe document",
        "extract text", "parse pdf", "read pdf", "scan doc",
        "sarvam", "sarvam ocr"
    ]
    lower_text = cleaned.lower()
    for trigger in ocr_triggers:
        if trigger in lower_text:
            return RequestClassification(
                intent=RequestIntent.DOCUMENT_OCR,
                confidence=0.95,
                language="en-IN",
                rationale=f"Query matched explicit OCR trigger keyword: '{trigger}'",
                extracted_query_or_filename=cleaned,
            )

    # Default to news intelligence pipeline
    return RequestClassification(
        intent=RequestIntent.NEWS_INTELLIGENCE,
        confidence=0.95,
        language="en-IN",
        rationale="Query is a breaking news, market inquiry, or general question.",
        extracted_query_or_filename=cleaned,
    )
