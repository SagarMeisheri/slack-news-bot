"""
Pydantic data models and schemas for the Multi-Agent News Intelligence System.
Adheres strictly to the guidelines, archetypes, and safety protocols in master_prompt.md,
and supports full ADK callback-based observability tracing.
"""

from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Safety & Suppression Schemas (Agent 1)
# ---------------------------------------------------------

class SuppressionStatus(str, Enum):
    NO_SUPPRESSION = "NO_SUPPRESSION"
    PARTIAL_SUPPRESSION = "PARTIAL_SUPPRESSION"
    FULL_SUPPRESSION = "FULL_SUPPRESSION"


class SafetyCategory(str, Enum):
    ACTIVE_EMERGENCY = "Active Emergencies & Mass Casualties"
    PRIVATE_AFFAIRS = "Private Health & Personal Affairs"
    MICRO_CAP_RUMORS = "Micro-Cap Stocks & Unverified Rumors"
    UNSUBSTANTIATED_CRIME = "Unsubstantiated Criminal Allegations"
    SUB_JUDICE = "Sub Judice & Contempt of Court"
    TERRITORIAL_INTEGRITY = "Territorial Integrity & Borders"
    COMMUNAL_HARMONY = "Communal, Caste & Religious Harmony"
    DEFAMATION_BNS = "Defamation & Character Imputation"
    FINANCIAL_REGULATIONS = "Financial & Market Regulations (SEBI/RBI)"
    ELECTIONS_MCC = "Elections & Model Code of Conduct"
    FACT_CHECKING = "Fact-Checking & State Notifications"
    SAFE = "Safe / No Violation"


class SafetyCheckResult(BaseModel):
    status: SuppressionStatus = Field(
        default=SuppressionStatus.NO_SUPPRESSION,
        description="Suppression verdict: FULL_SUPPRESSION, PARTIAL_SUPPRESSION, or NO_SUPPRESSION",
    )
    categories_triggered: List[SafetyCategory] = Field(
        default_factory=list,
        description="List of triggered safety/legal categories",
    )
    rationale: str = Field(
        default="",
        description="Detailed legal/safety analysis explaining the suppression or clearance",
    )
    suppressed_elements: List[str] = Field(
        default_factory=list,
        description="Specific sub-topics or questions prohibited under partial suppression",
    )
    safe_elements: List[str] = Field(
        default_factory=list,
        description="Safe topic elements permitted for baseline brief & grounded inquiry",
    )
    safety_notice: Optional[str] = Field(
        default=None,
        description="Formatted safety disclaimer text to display per Section 3",
    )


# ---------------------------------------------------------
# Agent Search Findings Schemas (Agents 2, 3, 4)
# ---------------------------------------------------------

class BreakingFindings(BaseModel):
    stage1_summary: str = Field(..., description="Synthesized Stage 1 core factual event and ground truth date")
    core_event_date: Optional[str] = Field(default=None, description="Explicit date of the core event (e.g. August 24, 2026)")
    stage2_summary: str = Field(..., description="Synthesized Stage 2 immediate market/sector fallout and stakeholder reactions")
    key_metrics: List[str] = Field(default_factory=list, description="Concrete metrics, figures, or percentage movements")
    source_conflicts: List[str] = Field(default_factory=list, description="Any discrepancy identified among reporting sources")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted URL citations")


class PrecedentFindings(BaseModel):
    stage3_precedent_summary: str = Field(..., description="Synthesized Stage 3 statutory history, prior doctrines, structural roots")
    stage4_counter_summary: str = Field(..., description="Synthesized Stage 4 critics, dissenters, and competing stakeholder arguments")
    stage5_analogous_summary: str = Field(..., description="Synthesized Stage 5 analogous cross-domain precedents")
    base_rate_notes: Optional[str] = Field(default=None, description="Calibrated base rate / frequency analysis for tail risks")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted URL citations")


class CalendarFindings(BaseModel):
    stage6_calendar_summary: str = Field(..., description="Synthesized Stage 6 forward calendar milestones")
    upcoming_dates: List[str] = Field(default_factory=list, description="Concrete upcoming dates and deadlines (e.g. September 15, 2026: SEBI filing deadline)")
    stage7_primary_source_summary: str = Field(..., description="Synthesized Stage 7 primary source filings, official gazettes, or notifications")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted URL citations")


# ---------------------------------------------------------
# Search Stage Result for UI & Analysis
# ---------------------------------------------------------

class SearchStageResult(BaseModel):
    stage_id: int = Field(..., description="Stage number from 1 to 7")
    stage_name: str = Field(..., description="Human-readable stage title")
    time_window: str = Field(..., description="Target search time window (e.g., Strict: 0-7 days)")
    objective: str = Field(..., description="Search objective description")
    queries_executed: List[str] = Field(default_factory=list, description="Queries sent to Parallel Search")
    findings_summary: str = Field(default="", description="Synthesized factual findings from this stage")
    excerpts: List[str] = Field(default_factory=list, description="Raw key quotes & facts extracted")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="URL citations with titles and dates")
    source_conflicts: List[str] = Field(default_factory=list, description="Discrepancies identified among sources")
    is_thin_evidence: bool = Field(default=False, description="True if credible results were sparse or missing")
    evidence_note: Optional[str] = Field(default=None, description="Explicit note on gaps or source discrepancies")


# ---------------------------------------------------------
# Baseline Brief & Inquiry Schemas (Agent 5)
# ---------------------------------------------------------

class BaselineBrief(BaseModel):
    core_event: str = Field(
        ...,
        description="1-2 factual sentences detailing core event and entities, citing verified sources/dates",
    )
    core_event_date: Optional[str] = Field(
        default=None,
        description="Ground truth date of the primary event",
    )
    immediate_fallout: str = Field(
        ...,
        description="1 sentence summarizing market, stakeholder, or regulatory reactions with concrete metrics",
    )
    context_precedent: str = Field(
        ...,
        description="1 sentence anchoring the event to historical precedent or existing statutory frameworks",
    )
    evidence_note: Optional[str] = Field(
        default=None,
        description="Flag any stage with insufficient data or source conflict per Section 4",
    )
    top_headlines: List[str] = Field(
        default_factory=list,
        description="Top 3-5 verified breaking headlines with markdown source links",
    )


class InquiryArchetype(str, Enum):
    WHY_X = "Why X? (Incentives & Timing)"
    WHAT_IT_MEANS = "What It Means (Second-Order Impact)"
    WHO_BENEFITS_LOSES = "Who Benefits / Who Loses"
    BLINDSPOT_WHAT_IF = "Blindspot / What If (Tail Risks)"
    WHAT_DOESNT_ADD_UP = "What Doesn't Add Up (Inconsistency)"
    WHAT_TO_WATCH = "What to Watch (Leading Indicators)"
    PRECEDENT_SAYS = "Precedent Says (Base Rate)"
    CROSS_BORDER_SPILLOVER = "Cross-Border / Cross-Sector Spillover"


class SpeculativeInquiry(BaseModel):
    archetype: InquiryArchetype = Field(..., description="The inquiry archetype")
    question: str = Field(..., description="Falsifiable single-sentence inquiry probing distinct angle")
    answer: Optional[str] = Field(
        default=None,
        description="2-3 sentence synthesized scenario projection/analysis with inline citations [Source](URL)",
    )
    source_stages: List[int] = Field(..., description="Traceable search stage IDs grounding this inquiry")
    neutrality_verified: bool = Field(
        default=True,
        description="Passes neutrality check (does not presuppose wrongdoing or intent)",
    )
    grounding_anchor: Optional[str] = Field(
        default=None,
        description="The specific date, filing, entity, metric, or precedent grounding the question",
    )


class SynthesisOutput(BaseModel):
    executive_summary: Optional[str] = Field(
        default=None,
        description="1-paragraph high-level strategic takeaway / executive TL;DR",
    )
    top_headlines: List[str] = Field(
        default_factory=list,
        description="Top 3-5 breaking headlines with markdown links [Headline](URL)",
    )
    baseline_brief: BaselineBrief = Field(..., description="Crisp date-grounded baseline intelligence brief")
    inquiries: List[SpeculativeInquiry] = Field(default_factory=list, description="10-20 grounded speculative inquiries with answers")
    formatted_markdown: str = Field(..., description="Rendered markdown output matching master_prompt.md Section 6")


# ---------------------------------------------------------
# Observability & Tracing Schemas
# ---------------------------------------------------------

class ToolCallTrace(BaseModel):
    tool_name: str = Field(..., description="Name of the invoked ADK tool")
    agent_name: str = Field(default="", description="Agent that called this tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Input parameters passed to the tool")
    result_summary: str = Field(default="", description="Summary or excerpt of tool return value")
    raw_result: Optional[Any] = Field(default=None, description="Full raw result data")
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = Field(default=0.0, description="Tool execution duration in milliseconds")
    is_success: bool = True
    error_message: Optional[str] = None


class ModelCallTrace(BaseModel):
    agent_name: str = Field(..., description="Agent name invoking LLM")
    model: str = Field(default="gemini-2.5-flash", description="Model name")
    prompt_preview: str = Field(default="", description="Preview snippet of prompt or user message")
    response_preview: str = Field(default="", description="Preview snippet of model output")
    thinking_trace: Optional[str] = Field(default=None, description="Reasoning thinking trace/thought tokens generated by Gemini")
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = Field(default=0.0)
    is_success: bool = True
    error_message: Optional[str] = None


class AgentExecutionTrace(BaseModel):
    agent_name: str = Field(..., description="Name of the ADK agent")
    description: str = Field(default="", description="Agent description")
    status: str = "pending"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_seconds: float = 0.0
    tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    model_calls: List[ModelCallTrace] = Field(default_factory=list)
    thinking_traces: List[str] = Field(default_factory=list, description="Extracted reasoning thought traces for this agent")
    output_key: Optional[str] = None
    output_summary: Optional[str] = None
    error: Optional[str] = None


class PipelineObservabilityReport(BaseModel):
    pipeline_name: str = Field(default="NewsIntelligencePipeline")
    topic: str = Field(default="")
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    total_duration_seconds: float = 0.0
    agent_traces: Dict[str, AgentExecutionTrace] = Field(default_factory=dict)
    total_tool_calls: int = 0
    total_model_calls: int = 0
    is_successful: bool = True
    error_message: Optional[str] = None


# ---------------------------------------------------------
# Top-Level Report & Progress
# ---------------------------------------------------------

class IntelligenceReport(BaseModel):
    query_topic: str = Field(..., description="Original user topic or breaking query")
    jurisdiction: str = Field(default="India", description="Selected jurisdiction focus")
    executive_summary: Optional[str] = Field(
        default=None,
        description="Executive TL;DR & high-level strategic takeaway",
    )
    top_headlines: List[str] = Field(
        default_factory=list,
        description="Top 3-5 verified breaking headlines with markdown links",
    )
    safety_result: SafetyCheckResult = Field(..., description="Safety and suppression audit result")
    search_stages: List[SearchStageResult] = Field(default_factory=list, description="All 7 search stage outputs")
    baseline_brief: Optional[BaselineBrief] = Field(default=None, description="Crisp date-grounded baseline brief")
    inquiries: List[SpeculativeInquiry] = Field(default_factory=list, description="10-20 grounded speculative inquiries")
    citations_all: List[Dict[str, Any]] = Field(default_factory=list, description="Consolidated unique citation links")
    formatted_markdown: str = Field(default="", description="Rendered markdown output matching master_prompt.md Section 6")
    execution_time_seconds: float = Field(default=0.0, description="Total execution duration in seconds")
    observability_report: Optional[PipelineObservabilityReport] = Field(
        default=None,
        description="Comprehensive ADK callback observability report",
    )


class AgentStepLog(BaseModel):
    agent_id: str
    agent_name: str
    status: str = "running"
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class PipelineProgressState(BaseModel):
    current_agent_index: int = 0
    total_agents: int = 5
    logs: List[AgentStepLog] = Field(default_factory=list)
    is_completed: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------
# Request Classification & OCR Schemas
# ---------------------------------------------------------

class RequestIntent(str, Enum):
    NEWS_INTELLIGENCE = "news_request"
    DOCUMENT_OCR = "ocr_request"


class RequestClassification(BaseModel):
    """Classification of an incoming Slack message or event."""
    intent: RequestIntent = Field(
        default=RequestIntent.NEWS_INTELLIGENCE,
        description="Classified request intent: news_request or ocr_request",
    )
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Confidence score for the classification",
    )
    language: Optional[str] = Field(
        default="en-IN",
        description="Detected document/text language code (e.g. en-IN, hi-IN)",
    )
    rationale: str = Field(
        default="",
        description="Reasoning behind routing classification",
    )
    extracted_query_or_filename: Optional[str] = Field(
        default=None,
        description="Cleaned topic query or target filename",
    )


class OCRProcessingResult(BaseModel):
    """Result of Sarvam Document OCR digitization."""
    filename: str = Field(..., description="Name of the digitized document")
    content_type: str = Field(default="application/pdf", description="Document MIME type")
    markdown_content: str = Field(default="", description="Full extracted markdown text with tables")
    page_count: Optional[int] = Field(default=None, description="Estimated page count if available")
    table_count: int = Field(default=0, description="Number of extracted tables")
    execution_time_seconds: float = Field(default=0.0, description="Processing duration in seconds")
    language: str = Field(default="en-IN", description="Language used for digitization")
    truncated: bool = Field(default=False, description="Whether display content was truncated for Slack message limits")
    file_upload_required: bool = Field(default=False, description="Whether a .md file attachment was uploaded")
    json_filepath: Optional[str] = Field(default=None, description="Saved local path to raw JSON output")
    md_filepath: Optional[str] = Field(default=None, description="Saved local path to Markdown output")
    error: Optional[str] = Field(default=None, description="Error message if processing failed")


