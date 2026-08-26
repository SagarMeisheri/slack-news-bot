"""
Search Tool & Stage Query Executor.
Integrates with Parallel Search API (parallel_client.py) adhering strictly to the 7-stage search execution defined in master_prompt.md.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from parallel_client import (
    search_parallel,
    format_parallel_results_as_context,
    ParallelSearchResponse,
)
from schemas.models import SearchStageResult

logger = logging.getLogger(__name__)

# Master 7-Stage Search Definitions as per master_prompt.md Section 4
STAGE_DEFINITIONS: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "Breaking Ground Truth",
        "time_window": "Strict: 0–7 days",
        "focus": "Primary event, official filings, regulatory orders, verified ministry statements",
        "query_template": '"{topic}" (breaking OR latest OR statement OR filing OR ruling OR announced OR PIB) ("this week" OR "past 7 days")',
        "feeds": "Baseline Brief",
    },
    2: {
        "name": "Immediate Fallout & Stakeholders",
        "time_window": "Strict: 0–7 days",
        "focus": "Market reactions, sectoral impact, official counter-statements, trade shifts",
        "query_template": '"{topic}" (impact OR reaction OR losses OR surge OR backlash OR affected OR sector) ("past 7 days" OR "today")',
        "feeds": "Baseline Brief; What It Means; Who Benefits / Who Loses",
    },
    3: {
        "name": "Precedent & Regulatory Context",
        "time_window": "All-time",
        "focus": "Statutory history, previous tribunal/court doctrines, policy cycles, structural causes",
        "query_template": '"{topic}" (precedent OR history OR "historical comparison" OR doctrine OR "root cause" OR policy)',
        "feeds": "Baseline Brief; Precedent Says",
    },
    4: {
        "name": "Adversarial / Counter-Narrative",
        "time_window": "0–30 days",
        "focus": "Critics, opposing stakeholders, competitors, dissenting officials — not just primary announcer framing",
        "query_template": '"{topic}" (critics OR opposition OR competitor OR dissent OR pushback OR "alternative view" OR "responded to")',
        "feeds": "Why X? (Incentives & Timing); Who Benefits / Who Loses",
    },
    5: {
        "name": "Analogous / Cross-Domain Precedent",
        "time_window": "All-time",
        "focus": "Structurally similar situations in other sectors, companies, or countries + frequency / base rate",
        "query_template": '"{topic}" (similar case OR "case study" OR comparable OR parallel OR "when happened" OR "base rate")',
        "feeds": "Blindspot / What If (Tail Risks); Precedent Says; Cross-Border Spillover",
    },
    6: {
        "name": "Forward Calendar / Scheduled Events",
        "time_window": "Now–90 days",
        "focus": "Concrete near-term dates: hearings, earnings calls, regulatory deadlines, policy reviews, elections",
        "query_template": '"{topic}" (schedule OR "next hearing" OR "results date" OR deadline OR "expected in" OR "due by")',
        "feeds": "What to Watch (Leading Indicators)",
    },
    7: {
        "name": "Primary Source / Site-Restricted",
        "time_window": "Conditional — regulatory, legal, financial",
        "focus": "Direct official filings rather than news paraphrase",
        "query_template": '"{topic}" (site:pib.gov.in OR site:sebi.gov.in OR site:rbi.org.in OR site:bseindia.com OR site:gov.in)',
        "feeds": "Baseline Brief citation quality; Why X?",
    },
}


def generate_stage_queries(topic: str, stage_id: int, custom_subtopic: Optional[str] = None) -> List[str]:
    """
    Generates targeted keyword queries for a given stage adhering to master_prompt.md patterns.
    """
    clean_topic = topic.strip().strip('"')
    sub = custom_subtopic.strip() if custom_subtopic else clean_topic

    if stage_id == 1:
        return [
            f'"{clean_topic}" news today',
            f'"{clean_topic}" news this week',
            f'"{clean_topic}" breaking news latest statement announced',
            f'"{clean_topic}" official filing order notification past 7 days',
        ]
    elif stage_id == 2:
        return [
            f'"{clean_topic}" market reaction news today',
            f'"{clean_topic}" immediate fallout this week',
            f'"{clean_topic}" stakeholder backlash losses surge',
            f'"{clean_topic}" competitor response trade shift',
        ]
    elif stage_id == 3:
        return [
            f'"{clean_topic}" statutory precedent history policy',
            f'"{clean_topic}" regulatory doctrine tribunal order root cause',
            f'"{clean_topic}" historical comparison past dispute',
        ]
    elif stage_id == 4:
        return [
            f'"{clean_topic}" critics opposition pushback dissent',
            f'"{clean_topic}" competitor alternative view response',
            f'"{clean_topic}" counter narrative challenge skepticism',
        ]
    elif stage_id == 5:
        return [
            f'"{sub}" similar case comparable parallel past outcome',
            f'"{sub}" analogous scenario case study lessons base rate',
            f'"{sub}" industry spillover cross domain historical precedent',
        ]
    elif stage_id == 6:
        return [
            f'"{clean_topic}" schedule next hearing results date deadline',
            f'"{clean_topic}" expected timeline regulatory decision due by',
            f'"{clean_topic}" upcoming calendar milestone next 90 days',
        ]
    elif stage_id == 7:
        return [
            f'"{clean_topic}" site:pib.gov.in',
            f'"{clean_topic}" site:rbi.org.in OR site:sebi.gov.in',
            f'"{clean_topic}" official gazette circular notification',
        ]
    else:
        return [f'"{clean_topic}" news latest updates']


async def execute_stage_search(
    stage_id: int,
    topic: str,
    custom_queries: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    mode: str = "fast",
    max_results: int = 6,
    timeout_seconds: float = 18.0,
) -> SearchStageResult:
    """
    Executes search for a specific stage using Parallel Search API and structures the output.
    """
    stage_meta = STAGE_DEFINITIONS.get(stage_id, {
        "name": f"Stage {stage_id}",
        "time_window": "Recent",
        "focus": "General search",
        "feeds": "General context",
    })

    queries = custom_queries if custom_queries else generate_stage_queries(topic, stage_id)
    objective = f"Stage {stage_id} ({stage_meta['name']}): {stage_meta['focus']} for topic: '{topic}'"

    logger.info(f"Executing Stage {stage_id} [{stage_meta['name']}] with queries: {queries}")

    search_resp: ParallelSearchResponse = await search_parallel(
        objective=objective,
        search_queries=queries,
        api_key=api_key,
        mode=mode,
        max_results=max_results,
        timeout_seconds=timeout_seconds,
    )

    excerpts: List[str] = []
    citations: List[Dict[str, Any]] = []

    if search_resp and search_resp.results:
        for res in search_resp.results:
            if res.excerpts:
                excerpts.extend(res.excerpts[:3])
            if res.url:
                citations.append({
                    "title": res.title or f"Source (Stage {stage_id})",
                    "url": res.url,
                    "publish_date": res.publish_date,
                    "stage_id": stage_id,
                    "stage_name": stage_meta["name"],
                })

    is_thin = len(excerpts) < 2
    evidence_note = None
    if is_thin:
        evidence_note = f"Stage {stage_id} ({stage_meta['name']}) returned sparse results. Inquiries relying on this stage will be flagged or calibrated accordingly."

    # Build concise findings summary from excerpts
    findings_summary = "\n".join([f"- {exc.strip()}" for exc in excerpts[:5]]) if excerpts else "No direct evidence retrieved for this stage."

    return SearchStageResult(
        stage_id=stage_id,
        stage_name=stage_meta["name"],
        time_window=stage_meta["time_window"],
        objective=objective,
        queries_executed=queries,
        findings_summary=findings_summary,
        excerpts=excerpts,
        citations=citations,
        source_conflicts=[],
        is_thin_evidence=is_thin,
        evidence_note=evidence_note,
    )


def consolidate_citations(stages: List[SearchStageResult]) -> List[Dict[str, Any]]:
    """
    Deduplicates and consolidates all citations across search stages.
    """
    seen_urls = set()
    consolidated = []
    for st in stages:
        for cit in st.citations:
            url = cit.get("url", "").strip()
            if url and url not in seen_urls:
                seen_urls.add(url)
                consolidated.append(cit)
    return consolidated
