"""
Parallel Web Search API Client.
Executes natural language web searches and retrieves LLM-optimized excerpts via https://api.parallel.ai/v1/search.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

PARALLEL_API_URL = "https://api.parallel.ai/v1/search"
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
    Executes a web search request against the Parallel Search API.
    
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

    payload: Dict[str, Any] = {
        "objective": objective,
        "search_queries": clean_queries,
        "mode": mode,
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(PARALLEL_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            results: List[ParallelSearchResult] = []
            for item in data.get("results", []):
                results.append(
                    ParallelSearchResult(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        publish_date=item.get("publish_date"),
                        excerpts=item.get("excerpts", []) or [],
                    )
                )

            return ParallelSearchResponse(
                search_id=data.get("search_id"),
                results=results,
                session_id=data.get("session_id"),
                warnings=data.get("warnings"),
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Parallel Search API returned HTTP error {e.response.status_code}: {e.response.text}")
        return ParallelSearchResponse(search_id=None, results=[])
    except Exception as e:
        logger.error(f"Parallel Search API request failed: {e}")
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
    context_desc: str,
    context_type: str = "curation",
) -> Tuple[str, List[str]]:
    """
    Uses Gemini API to analyze the news topic or user input and synthesize:
    1. A precise, natural-language search objective.
    2. Exactly 2-4 diverse, high-utility keyword search queries (3-6 words each) tailored for Parallel Search API.
    """
    import json
    from google import genai

    if context_type == "article":
        system_instruction = (
            "You are an expert investigative journalist and search query planner. "
            "Given the headline, background preview, and investigative objective for a developing news story, "
            "generate: (1) A comprehensive search objective for deep investigative research, and "
            "(2) 3 to 4 distinct keyword search queries (3 to 6 words each) covering the core event, "
            "official statements/evidence, background context, and financial/policy impact. "
            "Respond ONLY with a valid JSON object in the format: {\"objective\": string, \"search_queries\": [string, string, ...]}"
        )
        user_prompt = f"Story Details for Deep-Dive Research:\n{context_desc}"
    else:
        system_instruction = (
            "You are a real-time news search query planner. "
            "Given the target topic or user query, generate: "
            "(1) A concise search objective to discover the latest breaking updates and verified facts, and "
            "(2) 2 to 3 distinct keyword search queries (3 to 6 words each) optimized for searching live web news. "
            "Respond ONLY with a valid JSON object in the format: {\"objective\": string, \"search_queries\": [string, string, ...]}"
        )
        user_prompt = f"Target Topic / Query:\n{context_desc}"

    try:
        client = genai.Client(api_key=api_key, vertexai=False, http_options={"api_version": "v1beta"})
        loop = asyncio.get_event_loop()

        def _call_gemini():
            return client.interactions.create(
                model=model,
                system_instruction=system_instruction,
                input=user_prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                },
                generation_config={
                    "thinking_level": "minimal",
                    "temperature": 0.2,
                },
                stream=False,
            )

        resp = await loop.run_in_executor(None, _call_gemini)
        raw_text = getattr(resp, "output_text", None) or ""
        if not raw_text and hasattr(resp, "steps"):
            for st in resp.steps:
                if hasattr(st, "content"):
                    for cb in st.content:
                        if getattr(cb, "type", None) == "text":
                            raw_text = getattr(cb, "text", "")
                            break

        if raw_text:
            parsed = json.loads(raw_text.strip())
            obj = parsed.get("objective", "").strip()
            queries = parsed.get("search_queries", [])
            clean_queries = [str(q).strip() for q in queries if str(q).strip()]
            if obj and clean_queries:
                return obj, clean_queries
    except Exception as e:
        logger.warning(f"Gemini query planning failed ({e}), using fallback heuristic planner")

    # Fallback if Gemini planning is unavailable
    if context_type == "article":
        fallback_obj = f"Find comprehensive facts, official statements, and background for: {context_desc[:120]}"
        fallback_queries = [
            f"{context_desc[:50]} latest news",
            f"{context_desc[:50]} verified report",
            f"{context_desc[:50]} developing updates",
        ]
    else:
        fallback_obj = f"Find top breaking news and developments on: {context_desc[:100]}"
        fallback_queries = [
            f"{context_desc[:50]} breaking news",
            f"{context_desc[:50]} updates today",
        ]
    return fallback_obj, fallback_queries

