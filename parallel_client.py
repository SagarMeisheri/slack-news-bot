"""
Parallel Web Search API Client.
Executes natural language web searches and retrieves LLM-optimized excerpts via official `parallel-web` SDK.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from parallel import AsyncParallel, Parallel, ParallelError

logger = logging.getLogger(__name__)

DEFAULT_PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY", "")


@dataclass
class ParallelSearchResult:
    url: str
    title: str
    publish_date: Optional[str] = None
    excerpts: List[str] = field(default_factory=list)


@dataclass
class ParallelSearchResponse:
    search_id: Optional[str]
    results: List[ParallelSearchResult] = field(default_factory=list)
    session_id: Optional[str] = None
    warnings: Optional[Any] = None


async def search_parallel(
    objective: str,
    search_queries: List[str],
    api_key: Optional[str] = None,
    mode: str = "fast",
    max_results: int = 10,
    timeout_seconds: float = 15.0,
) -> ParallelSearchResponse:
    """
    Executes a web search request against the Parallel Search API using the official parallel-web SDK.
    
    Args:
        objective: Natural-language description of the search goal.
        search_queries: List of 1-5 keyword search queries (3-6 words each).
        api_key: Optional Parallel API key (defaults to PARALLEL_API_KEY from environment).
        mode: Search mode preset ('turbo', 'fast', 'basic', 'advanced'). Defaults to 'fast'.
        max_results: Maximum results to request.
        timeout_seconds: Request timeout in seconds.
    """
    key = api_key or os.getenv("PARALLEL_API_KEY") or DEFAULT_PARALLEL_API_KEY
    if not key:
        logger.warning("PARALLEL_API_KEY is not set. Skipping Parallel search.")
        return ParallelSearchResponse(search_id=None, results=[])

    clean_queries = [q.strip() for q in search_queries if q and q.strip()][:5]
    if not clean_queries:
        clean_queries = [objective[:100]]

    # Map mode if needed (turbo, basic, advanced, fast)
    sdk_mode = mode if mode in ("turbo", "basic", "advanced", "fast") else "fast"

    try:
        client = AsyncParallel(api_key=key, timeout=timeout_seconds)
        response = await client.search(
            search_queries=clean_queries,
            objective=objective,
            mode=sdk_mode,
        )

        results: List[ParallelSearchResult] = []
        for item in response.results:
            results.append(
                ParallelSearchResult(
                    url=item.url,
                    title=item.title or "",
                    publish_date=item.publish_date,
                    excerpts=item.excerpts or [],
                )
            )

        return ParallelSearchResponse(
            search_id=response.search_id,
            results=results,
            session_id=response.session_id,
            warnings=response.warnings,
        )

    except ParallelError as e:
        logger.error(f"Parallel Search SDK Error: {e}")
        return ParallelSearchResponse(search_id=None, results=[])
    except Exception as e:
        logger.error(f"Parallel Search request failed: {e}")
        return ParallelSearchResponse(search_id=None, results=[])



def format_parallel_results_as_context(
    response: ParallelSearchResponse,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Formats Parallel Search results into a structured Markdown grounding context block
    suitable for injecting into LLM user prompts, and returns a list of citation items.
    """
    if not response or not response.results:
        return "", []

    context_lines = [
        "## Real-Time Web Grounding Context (Source: Parallel Web Search)",
        "The following live web search results have been retrieved to ground your response with verified facts, sources, and dates:\n",
    ]

    citations: List[Dict[str, Any]] = []

    for idx, item in enumerate(response.results, 1):
        title = item.title.strip() if item.title else f"Web Source {idx}"
        url = item.url.strip()
        pub = f" (Published: {item.publish_date})" if item.publish_date else ""

        context_lines.append(f"### [{idx}] {title}{pub}")
        context_lines.append(f"**URL:** {url}")

        if item.excerpts:
            context_lines.append("**Excerpts & Verified Findings:**")
            for excerpt in item.excerpts:
                clean_excerpt = excerpt.strip()
                if clean_excerpt:
                    context_lines.append(f"> {clean_excerpt}\n")
        context_lines.append("")

        if url:
            citations.append({
                "type": "url_citation",
                "url": url,
                "title": title,
                "source_index": idx,
            })

    formatted_text = "\n".join(context_lines).strip()
    return formatted_text, citations


async def plan_parallel_search_queries_with_gemini(
    api_key: str,
    model: str,
    topic: str,
    initial_research: Optional[str] = None,
    stage_focus: str = "general",
) -> Tuple[str, List[str]]:
    """
    Uses Gemini LLM in a multi-agent setup to analyze initial research findings
    and synthesize guided, high-utility search objectives and keyword queries for Parallel Search.
    
    Args:
        api_key: Google Gemini API Key.
        model: Gemini model name.
        topic: The headline or topic under investigation.
        initial_research: Optional synthesized findings from Stage 1/2 Ground Truth.
        stage_focus: Target search stage focus ('precedent', 'counter', 'calendar', 'primary_sources', or 'general').
    """
    import json
    from google import genai
    from google.genai import types

    system_instruction = (
        "You are an expert investigative intelligence query planner in a multi-agent news verification system. "
        "Your task is to analyze the core topic along with any initial research findings already discovered, "
        "and formulate: (1) A razor-sharp, natural-language search objective, and "
        "(2) 2 to 4 concise, high-signal keyword search queries (3 to 6 words each) tailored for the Parallel Web Search API.\n"
        "Anchor your search queries strictly to the verified entity names, regulatory circulars, and specific dates "
        "identified in the initial research, avoiding generic or repetitive queries.\n"
        "Respond ONLY with a valid JSON object matching: {\"objective\": string, \"search_queries\": [string, string, ...]}"
    )

    if initial_research:
        user_prompt = (
            f"Topic: \"{topic}\"\n"
            f"Search Stage Focus: {stage_focus}\n\n"
            f"Initial Research Findings (Stage 1 & 2 Ground Truth):\n{initial_research}\n\n"
            f"Formulate a guided search objective and 2-4 targeted keyword probes drilling into the specific entities "
            f"and claims uncovered above."
        )
    else:
        user_prompt = (
            f"Topic: \"{topic}\"\n"
            f"Search Stage Focus: {stage_focus}\n\n"
            f"Formulate a breaking ground-truth search objective and 2-3 targeted keyword probes to verify what occurred."
        )

    try:
        client = genai.Client(api_key=api_key)
        loop = asyncio.get_event_loop()

        def _call_gemini():
            return client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

        resp = await loop.run_in_executor(None, _call_gemini)
        raw_text = resp.text if hasattr(resp, "text") else ""

        if raw_text:
            parsed = json.loads(raw_text.strip())
            obj = parsed.get("objective", "").strip()
            queries = parsed.get("search_queries", [])
            clean_queries = [str(q).strip() for q in queries if str(q).strip()]
            if obj and clean_queries:
                return obj, clean_queries
    except Exception as e:
        logger.warning(f"Gemini multi-agent query planning fallback ({e})")

    # Fallback heuristic planner if API is offline or dry-run
    if initial_research:
        fallback_obj = f"Investigate {stage_focus} context based on verified facts for: {topic[:100]}"
        fallback_queries = [
            f'"{topic[:40]}" {stage_focus} precedent',
            f'"{topic[:40]}" official filing order',
            f'"{topic[:40]}" timeline analysis',
        ]
    else:
        fallback_obj = f"Verify breaking ground truth and core event for: {topic[:100]}"
        fallback_queries = [
            f'"{topic[:40]}" news today',
            f'"{topic[:40]}" breaking updates',
        ]

    return fallback_obj, fallback_queries


