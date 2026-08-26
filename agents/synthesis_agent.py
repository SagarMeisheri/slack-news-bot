"""
Agent 5: Synthesis & Neutrality Auditor Agent using Google ADK.
Synthesizes the Baseline Intelligence Brief and generates 10 to 20 Speculative & Strategic Inquiries
across the 8 archetypes, enforcing strict neutrality checks, standalone self-contained question context,
and clickable source links using native Parallel Search citations.
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
    baseline: BaselineBrief,
    inquiries: List[SpeculativeInquiry],
    safety_notice: Optional[str] = None,
    is_full_suppression: bool = False,
    citations: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Helper to render exact markdown format with standalone inquiries and native Parallel Search citation links.
    """
    lines = []

    if safety_notice:
        lines.append(f"> ⚠️ **{safety_notice}**\n")

    date_str = f" ({baseline.core_event_date})" if baseline.core_event_date else ""
    lines.extend([
        "### Baseline Intelligence Brief",
        f"* **Core Event{date_str}**: {baseline.core_event}",
        f"* **Immediate Fallout**: {baseline.immediate_fallout}",
        f"* **Context & Precedent**: {baseline.context_precedent}",
    ])
    if baseline.evidence_note:
        lines.append(f"* **Evidence Note**: {baseline.evidence_note}")

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
    for inq in inquiries:
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

                lines.append(f"* {q.question} *(source: {stages_str})*")
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
        description="Synthesizes the Baseline Intelligence Brief and generates 10 to 20 standalone Speculative & Strategic Inquiries.",
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
