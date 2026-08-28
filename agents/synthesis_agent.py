"""
Agent 5: Synthesis & Neutrality Auditor Agent using Google ADK.
Synthesizes the Executive TL;DR, Baseline Intelligence Brief, and generates 10 to 20 Speculative & Strategic Inquiries
with Grounded Scenario Answers across the 8 archetypes, enforcing strict neutrality checks, standalone self-contained
context, and dual citation coverage (inline markdown links + full verified source references).
"""

from typing import Any, Dict, List, Optional
from config import ModelConfig, get_default_model_config
from google.adk.agents import LlmAgent
from observability.tracker import ObservabilityTracker
from prompts.loader import prompt_registry
from schemas.models import (
    BaselineBrief,
    InquiryArchetype,
    SpeculativeInquiry,
    SynthesisOutput,
)


def format_report_markdown(
    baseline: Optional[BaselineBrief] = None,
    inquiries: Optional[List[SpeculativeInquiry]] = None,
    executive_summary: Optional[str] = None,
    top_headlines: Optional[List[str]] = None,
    safety_notice: Optional[str] = None,
    is_full_suppression: bool = False,
    citations: Optional[List[Dict[str, Any]]] = None,
    topic: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    safety_result: Optional[Any] = None,
    baseline_brief: Optional[BaselineBrief] = None,
    social_findings: Optional[Any] = None,
    **kwargs: Any,
) -> str:

    """
    Helper to render exact markdown format with executive summary, top headlines,
    baseline brief, standalone inquiries, grounded scenario answers with embedded inline citations,
    and verified references.
    """
    effective_baseline = baseline or baseline_brief or BaselineBrief(
        core_event=topic or "Event analysis",
        immediate_fallout="Assessing multi-stakeholder outcomes",
        context_precedent="Synthesizing historical precedents",
    )
    effective_inquiries = inquiries if inquiries is not None else []

    lines = []

    if safety_notice:
        lines.append(f"> ⚠️ **{safety_notice}**\n")


    # 1. Executive TL;DR & Strategic Takeaway
    if executive_summary:
        raw_summary_lines = [l.strip() for l in executive_summary.strip().split("\n") if l.strip()]
        md_summary_bullets = []
        for l in raw_summary_lines:
            if l.startswith(("*", "-", "•", "–", "—")):
                clean_l = re.sub(r"^[\*\-\•\–\—]+\s*", "", l)
                md_summary_bullets.append(f"* {clean_l}")
            else:
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'‘“])", l) if s.strip()]
                for s in sentences:
                    md_summary_bullets.append(f"* {s}")
        lines.extend([
            "### Executive Summary & Strategic Takeaway",
            *md_summary_bullets,
            "",
            "---",
            "",
        ])


    # 2. Top Breaking Headlines
    headlines = top_headlines or getattr(effective_baseline, "top_headlines", None)
    if headlines:
        lines.extend([
            "### 📰 Top Breaking Headlines",
            *[f"* {h.lstrip('* ')}" for h in headlines],
            "",
            "---",
            "",
        ])
    elif citations:
        seen_hl_urls = set()
        hl_items = []
        for c in citations[:4]:
            u = c.get("url")
            t = c.get("title")
            p = c.get("source_domain") or "Verified Source"
            d = f" ({c.get('publish_date')})" if c.get("publish_date") else ""
            if u and u not in seen_hl_urls and t:
                seen_hl_urls.add(u)
                hl_items.append(f"* [{t}]({u}) — *{p}{d}*")
        if hl_items:
            lines.extend([
                "### 📰 Top Breaking Headlines",
                *hl_items,
                "",
                "---",
                "",
            ])

    # 3. Baseline Intelligence Brief
    date_str = f" ({effective_baseline.core_event_date})" if effective_baseline.core_event_date else ""
    lines.extend([
        "### Baseline Intelligence Brief",
        f"* **Core Event{date_str}**: {effective_baseline.core_event}",
        f"* **Immediate Fallout**: {effective_baseline.immediate_fallout}",
        f"* **Context & Precedent**: {effective_baseline.context_precedent}",
    ])
    if effective_baseline.evidence_note:
        lines.append(f"* **Evidence Note**: {effective_baseline.evidence_note}")

    # 4. Public Sentiment & Social Media Buzz (if present)
    soc_findings = social_findings or kwargs.get("social_findings")
    if soc_findings:
        overview = getattr(soc_findings, "sentiment_overview", None) or (soc_findings.get("sentiment_overview") if isinstance(soc_findings, dict) else None)
        narratives = getattr(soc_findings, "dominant_narratives", []) or (soc_findings.get("dominant_narratives", []) if isinstance(soc_findings, dict) else [])
        claims = getattr(soc_findings, "viral_claims_or_memes", []) or (soc_findings.get("viral_claims_or_memes", []) if isinstance(soc_findings, dict) else [])
        quotes = getattr(soc_findings, "community_quotes", []) or (soc_findings.get("community_quotes", []) if isinstance(soc_findings, dict) else [])

        soc_lines = ["", "---", "", "### 💬 Public Sentiment & Social Media Buzz"]
        if overview:
            soc_lines.append(f"* **Community Mood**: {overview}")
        for narr in narratives[:3]:
            soc_lines.append(f"* **Prevailing Narrative**: {narr}")
        for clm in claims[:2]:
            soc_lines.append(f"* **Viral Claim / Buzz**: {clm}")
        for q in quotes[:2]:
            soc_lines.append(f"* **Community Voice**: _{q}_")
        lines.extend(soc_lines)

    # Full suppression early return with references
    if is_full_suppression:
        if citations:
            lines.extend(["", "---", "", "### 🔗 Verified Source References", ""])
            seen_urls = set()
            for cit in citations:
                url = cit.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                title = cit.get("title") or "Source Document"
                stage = cit.get("stage_name") or f"Stage {cit.get('stage_id', 'Finding')}"
                pub = f" ({cit.get('publish_date')})" if cit.get("publish_date") else ""
                lines.append(f"* [{title}]({url}) — *{stage}{pub}*")
        return "\n".join(lines)

    lines.extend(["", "---", "", "### Speculative & Strategic Inquiries", ""])


    archetype_groups = {arch: [] for arch in InquiryArchetype}
    for inq in effective_inquiries:
        if inq.archetype in archetype_groups:
            archetype_groups[inq.archetype].append(inq)
        else:
            archetype_groups[InquiryArchetype.WHY_X].append(inq)


    archetype_order = [
        (InquiryArchetype.WHY_X, "Why X? (Incentives & Timing)"),
        (InquiryArchetype.WHAT_IT_MEANS, "What It Means (Second-Order Impact)"),
        (InquiryArchetype.WHO_BENEFITS_LOSES, "Who Benefits / Who Loses"),
        (InquiryArchetype.BLINDSPOT_WHAT_IF, "Blindspot / What If (Tail Risks)"),
        (InquiryArchetype.WHAT_DOESNT_ADD_UP, "What Doesn't Add Up (Inconsistency)"),
        (InquiryArchetype.WHAT_TO_WATCH, "What to Watch (Leading Indicators)"),
        (InquiryArchetype.PRECEDENT_SAYS, "Precedent Says (Base Rate)"),
        (InquiryArchetype.CROSS_BORDER_SPILLOVER, "Cross-Border / Cross-Sector Spillover"),
    ]

    # Map stage IDs to citations returned by Parallel Search
    stage_to_cits: Dict[int, List[Dict[str, Any]]] = {}
    all_clean_cits: List[Dict[str, Any]] = []
    if citations:
        for cit in citations:
            url = cit.get("url")
            if not url:
                continue
            all_clean_cits.append(cit)
            sid = cit.get("stage_id")
            if sid:
                try:
                    int_sid = int(sid)
                    stage_to_cits.setdefault(int_sid, []).append(cit)
                except (ValueError, TypeError):
                    pass

    cit_index = 0
    for arch_enum, title in archetype_order:
        group = archetype_groups.get(arch_enum, [])
        if not group and arch_enum == InquiryArchetype.WHAT_DOESNT_ADD_UP:
            continue

        lines.append(f"**{title}**")
        if not group:
            lines.append(f"* *No grounded inquiry generated for this archetype.*")
        else:
            for q in group:
                source_links = []
                seen_link_urls = set()

                # Gather source links matching the query's source stages directly from Parallel citations
                if q.source_stages:
                    for s in q.source_stages:
                        matching = stage_to_cits.get(s, [])
                        for m_cit in matching:
                            m_url = m_cit.get("url")
                            if m_url and m_url not in seen_link_urls:
                                seen_link_urls.add(m_url)
                                m_title = m_cit.get("title") or f"Source {s}"
                                source_links.append(f"[{m_title}]({m_url})")
                                if len(source_links) >= 2:
                                    break

                # Fallback to general Parallel citations pool if no specific stage match
                if not source_links and all_clean_cits:
                    fallback_cit = all_clean_cits[cit_index % len(all_clean_cits)]
                    cit_index += 1
                    f_url = fallback_cit.get("url")
                    if f_url:
                        f_title = fallback_cit.get("title") or "Source Reference"
                        source_links.append(f"[{f_title}]({f_url})")

                if source_links:
                    stages_str = ", ".join(source_links)
                else:
                    stages_str = "Verified Intelligence Source"

                # Render Question + Scenario Projection/Answer with Inline Citations
                lines.append(f"* **Inquiry**: {q.question}")
                if q.answer:
                    # If the answer already contains markdown link format, preserve it, else append citation link
                    if "http" in q.answer or "[" in q.answer:
                        lines.append(f"  **Scenario Projection**: {q.answer}")
                    else:
                        lines.append(f"  **Scenario Projection**: {q.answer} *(sources: {stages_str})*")
                else:
                    lines.append(f"  *(Grounding Source: {stages_str})*")
        lines.append("")

    # Add Source References Section directly with Parallel Search titles and links
    if citations:
        lines.extend(["---", "", "### 🔗 Verified Source References", ""])
        seen_urls = set()
        for cit in citations:
            url = cit.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = cit.get("title") or "Source Reference"
            stage = cit.get("stage_name") or f"Stage {cit.get('stage_id', '')} Finding"
            if stage.strip() in ["Stage", "Stage Finding", "Stage "]:
                stage = "Verified Search Finding"
            pub = f" ({cit.get('publish_date')})" if cit.get("publish_date") else ""
            lines.append(f"* [{title}]({url}) — *{stage}{pub}*")

    return "\n".join(lines).strip()


def create_synthesis_agent(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    jurisdiction: str = "India",
    name: str = "Synthesis_Neutrality_Auditor",
    tracker: Optional[ObservabilityTracker] = None,
) -> LlmAgent:
    """Creates the ADK Synthesis & Neutrality Auditor Agent with ModelConfig and thinking levels."""
    cfg = model_config or get_default_model_config(model_name=model)
    instruction = prompt_registry.get_synthesis_prompt(jurisdiction=jurisdiction)

    return LlmAgent(
        name=name,
        description="Synthesizes the Executive TL;DR, Baseline Brief, and generates 10 to 20 standalone Speculative Inquiries with Grounded Scenario Answers and inline citations.",
        model=cfg.model_name,
        generate_content_config=cfg.to_generate_content_config(),
        instruction=instruction,
        output_schema=SynthesisOutput,
        output_key="synthesis_output",
        before_agent_callback=tracker.on_before_agent if tracker else None,
        after_agent_callback=tracker.on_after_agent if tracker else None,
        before_model_callback=tracker.on_before_model if tracker else None,
        after_model_callback=tracker.on_after_model if tracker else None,
        before_tool_callback=tracker.on_before_tool if tracker else None,
        after_tool_callback=tracker.on_after_tool if tracker else None,
    )
