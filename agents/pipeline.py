"""
ADK Pipeline Module.
Assembles the 5 specialized LlmAgents into a deterministic ADK SequentialAgent
and provides master intent routing between Sarvam Document OCR and News Intelligence.
"""

import logging
from typing import List, Optional, Tuple, Union
from config import ModelConfig, get_default_model_config
from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner
from agents.breaking_agent import create_breaking_agent
from agents.calendar_agent import create_calendar_agent
from agents.classifier_agent import classify_incoming_request, create_classifier_agent
from agents.ocr_agent import execute_sarvam_ocr_job
from agents.precedent_agent import create_precedent_agent
from agents.safety_agent import create_safety_agent
from agents.social_agent import create_social_agent
from agents.synthesis_agent import create_synthesis_agent
from observability.tracker import ObservabilityTracker
from schemas.models import RequestClassification, RequestIntent

logger = logging.getLogger(__name__)


def build_adk_news_pipeline(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    jurisdiction: str = "India",
    app_name: str = "news_intelligence_pipeline",
    tracker: Optional[ObservabilityTracker] = None,
    resume_state: Optional[dict] = None,
) -> Tuple[SequentialAgent, InMemoryRunner, ObservabilityTracker]:
    """
    Constructs the 6-agent ADK Sequential Pipeline with ModelConfig and Thinking levels.
    If resume_state is provided, agents whose outputs are already present in resume_state
    are skipped to avoid redundant execution or search API calls.

    Returns:
        (pipeline_agent, runner, tracker)
    """
    cfg = model_config or get_default_model_config(model_name=model)
    obs_tracker = tracker or ObservabilityTracker(pipeline_name=app_name)

    sub_agents = []

    # 1. Safety & Triage Agent
    if not (resume_state and resume_state.get("safety_result")):
        safety_agent = create_safety_agent(model_config=cfg, jurisdiction=jurisdiction, tracker=obs_tracker)
        sub_agents.append(safety_agent)

    # 2. Breaking & Fallout Investigator
    if not (resume_state and resume_state.get("stages_1_2")):
        breaking_agent = create_breaking_agent(model_config=cfg, tracker=obs_tracker)
        sub_agents.append(breaking_agent)

    # 3. Precedent & Counter-Narrative Investigator
    if not (resume_state and resume_state.get("stages_3_5")):
        precedent_agent = create_precedent_agent(model_config=cfg, tracker=obs_tracker)
        sub_agents.append(precedent_agent)

    # 4. Social Media & Public Sentiment Investigator
    if not (resume_state and resume_state.get("stages_8")):
        social_agent = create_social_agent(model_config=cfg, tracker=obs_tracker)
        sub_agents.append(social_agent)

    # 5. Forward Calendar & Primary Source Investigator
    if not (resume_state and resume_state.get("stages_6_7")):
        calendar_agent = create_calendar_agent(model_config=cfg, tracker=obs_tracker)
        sub_agents.append(calendar_agent)

    # 6. Synthesis & Neutrality Auditor
    if not (resume_state and resume_state.get("synthesis_output")):
        synthesis_agent = create_synthesis_agent(model_config=cfg, jurisdiction=jurisdiction, tracker=obs_tracker)
        sub_agents.append(synthesis_agent)

    # Fallback to synthesis_agent if all stages are already present
    if not sub_agents:
        synthesis_agent = create_synthesis_agent(model_config=cfg, jurisdiction=jurisdiction, tracker=obs_tracker)
        sub_agents.append(synthesis_agent)

    pipeline_agent = SequentialAgent(
        name="NewsIntelligencePipeline",
        description="Sequential 6-agent pipeline for safety triage, 1-call search investigation, social sentiment, and scenario analysis synthesis.",
        sub_agents=sub_agents,
    )

    runner = InMemoryRunner(
        agent=pipeline_agent,
        app_name=app_name,
    )

    return pipeline_agent, runner, obs_tracker



async def classify_and_route(
    text: str,
    has_files: bool = False,
    file_names: Optional[List[str]] = None,
    model_config: Optional[ModelConfig] = None,
    tracker: Optional[ObservabilityTracker] = None,
) -> RequestClassification:
    """
    Master router using ADK Classifier:
    Determines whether an incoming event routes to Sarvam OCR or News Intelligence.
    """
    return await classify_incoming_request(
        text=text,
        has_files=has_files,
        file_names=file_names,
        model_config=model_config,
        tracker=tracker,
    )
