"""
ADK Tools Module (google.adk.tools).
Registers stage-specific FunctionTools wrapping Parallel Web Search API (parallel_client.py)
adhering strictly to master_prompt.md Section 4 search definitions.
Each agent evaluates context, formulates an explicit natural-language search objective
and specific search query terms, and executes its single search budget.
"""

import json
import logging
from typing import Dict, List, Optional
from google.adk.tools import FunctionTool
from parallel_client import ParallelSearchResponse, search_parallel
from tools.search_tool import STAGE_DEFINITIONS, generate_stage_queries

logger = logging.getLogger(__name__)


async def _run_stage_search_json(
    stage_id: int,
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_subtopic: Optional[str] = None,
    mode: str = "fast",
    max_results: int = 6,
) -> str:
    """
    Helper to execute stage search with both natural-language objective and targeted search terms.
    """
    stage_meta = STAGE_DEFINITIONS.get(stage_id, {
        "name": f"Stage {stage_id}",
        "time_window": "Recent",
        "focus": "General search",
    })

    # Generate institutional queries and prepend agent-provided custom search query if provided
    base_queries = generate_stage_queries(topic, stage_id, custom_subtopic)
    queries: List[str] = []

    if search_query and search_query.strip():
        queries.append(search_query.strip())

    for q in base_queries:
        if q not in queries:
            queries.append(q)

    # Use agent-provided objective if given, otherwise build stage-grounded objective
    final_objective = objective.strip() if objective and objective.strip() else (
        f"Stage {stage_id} ({stage_meta['name']} - Window: {stage_meta['time_window']}): "
        f"{stage_meta['focus']} for topic: '{topic}'"
    )

    logger.info(f"[ADK Tool] Executing Stage {stage_id} [{stage_meta['name']}] | Objective: '{final_objective[:100]}...' | Queries: {queries[:3]}")

    search_resp: ParallelSearchResponse = await search_parallel(
        objective=final_objective,
        search_queries=queries[:5],
        mode=mode,
        max_results=max_results,
    )

    excerpts: List[str] = []
    citations: List[Dict[str, str]] = []

    if search_resp and search_resp.results:
        for res in search_resp.results:
            if res.excerpts:
                excerpts.extend(res.excerpts[:3])
            if res.url:
                citations.append({
                    "title": res.title or f"Source (Stage {stage_id})",
                    "url": res.url,
                    "publish_date": res.publish_date or "",
                    "stage_id": str(stage_id),
                    "stage_name": stage_meta["name"],
                })

    output_data = {
        "stage_id": stage_id,
        "stage_name": stage_meta["name"],
        "time_window": stage_meta["time_window"],
        "objective": final_objective,
        "queries_executed": queries[:5],
        "verified_excerpts": excerpts[:6],
        "citations": citations[:6],
        "is_thin_evidence": len(excerpts) < 2,
    }
    return json.dumps(output_data, indent=2)


async def search_stage_1_ground_truth(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 1: Breaking Ground Truth Search (Strict: 0-7 days window).
    Retrieves primary event details, official filings, regulatory orders, verified ministry statements, and ground truth dates.

    Args:
        topic: The breaking news headline, entity name, or core topic.
        objective: Natural language description of the search goal (e.g. "Discover primary facts and calendar date for RBI digital lending order").
        search_query: Specific 3-6 word keyword search query (e.g. "RBI digital lending draft guidelines 2026").
        custom_focus: Optional entity name or subtopic to narrow the breaking ground truth search.
    """
    return await _run_stage_search_json(
        1,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


async def search_stage_2_immediate_fallout(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 2: Immediate Fallout & Stakeholders Search (Strict: 0-7 days window).
    Retrieves market reactions, stock/bond metrics, sectoral impact, official counter-statements, and trade shifts.

    Args:
        topic: The target event, entity, or affected sector.
        objective: Natural language description of the search goal (e.g. "Identify immediate market impact and industry reaction").
        search_query: Specific 3-6 word keyword search query (e.g. "NBFC bank stock reactions digital lending rules").
        custom_focus: Optional specific sector, market, or stakeholder to narrow the fallout search.
    """
    return await _run_stage_search_json(
        2,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


async def search_stage_3_precedent_history(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 3: Precedent & Regulatory Context Search (All-time window).
    Retrieves statutory history, previous tribunal/court doctrines, policy cycles, and structural root causes.

    Args:
        topic: The target entity, policy, or statutory topic.
        objective: Natural language description of the precedent search objective.
        search_query: Specific keyword query for statutory or legal precedent.
        custom_focus: Optional specific statute, prior case, or doctrine keyword.
    """
    return await _run_stage_search_json(
        3,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


async def search_stage_4_counter_narratives(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 4: Adversarial / Counter-Narrative Search (0-30 days window).
    Retrieves critics, opposing stakeholders, competitors, dissenting officials, and strategic timing skepticism.

    Args:
        topic: The target entity or controversial policy action.
        objective: Natural language description of the counter-narrative search objective.
        search_query: Specific keyword query targeting critics, dissenting views, or pushback.
        custom_focus: Optional specific competitor, critic group, or dissenting argument keyword.
    """
    return await _run_stage_search_json(
        4,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


async def search_stage_5_analogous_precedents(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    analogous_subtopic: Optional[str] = None,
) -> str:
    """Executes Stage 5: Analogous / Cross-Domain Precedent Search (All-time window).
    Retrieves structurally similar situations in other sectors/countries and historical base rates for tail risks.

    Args:
        topic: Primary topic.
        objective: Natural language description of the analogous cross-domain search objective.
        search_query: Specific keyword query for analogous case studies or base rates.
        analogous_subtopic: Optional specific analogous mechanism or cross-domain keyword.
    """
    return await _run_stage_search_json(
        5,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=analogous_subtopic,
    )


async def search_stage_6_forward_calendar(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 6: Forward Calendar / Scheduled Events Search (Now-90 days window).
    Retrieves concrete near-term milestone dates: hearings, earnings calls, regulatory deadlines, policy reviews.

    Args:
        topic: The target entity, court matter, or regulatory review.
        objective: Natural language description of the upcoming calendar events search objective.
        search_query: Specific keyword query for upcoming deadlines or hearings.
        custom_focus: Optional specific hearing, deadline, or results event keyword.
    """
    return await _run_stage_search_json(
        6,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


async def search_stage_7_primary_source_filings(
    topic: str,
    objective: Optional[str] = None,
    search_query: Optional[str] = None,
    custom_focus: Optional[str] = None,
) -> str:
    """Executes Stage 7: Primary Source / Site-Restricted Search (Conditional regulatory/legal).
    Retrieves direct official gazettes, SEBI/RBI circulars, and PIB government notifications.

    Args:
        topic: The regulatory circular, gazette notice, or corporate filing.
        objective: Natural language description of the official gazette/filing search objective.
        search_query: Specific keyword query including site filter (e.g. "site:rbi.org.in digital lending").
        custom_focus: Optional specific regulatory domain or site filter (e.g. sebi, rbi, pib).
    """
    return await _run_stage_search_json(
        7,
        topic,
        objective=objective,
        search_query=search_query,
        custom_subtopic=custom_focus,
    )


# ADK FunctionTool instances
tool_stage_1 = FunctionTool(search_stage_1_ground_truth)
tool_stage_2 = FunctionTool(search_stage_2_immediate_fallout)
tool_stage_3 = FunctionTool(search_stage_3_precedent_history)
tool_stage_4 = FunctionTool(search_stage_4_counter_narratives)
tool_stage_5 = FunctionTool(search_stage_5_analogous_precedents)
tool_stage_6 = FunctionTool(search_stage_6_forward_calendar)
tool_stage_7 = FunctionTool(search_stage_7_primary_source_filings)

BREAKING_TOOLS = [tool_stage_1, tool_stage_2]
PRECEDENT_TOOLS = [tool_stage_3, tool_stage_4, tool_stage_5]
CALENDAR_TOOLS = [tool_stage_6, tool_stage_7]
ALL_SEARCH_TOOLS = [
    tool_stage_1,
    tool_stage_2,
    tool_stage_3,
    tool_stage_4,
    tool_stage_5,
    tool_stage_6,
    tool_stage_7,
]
