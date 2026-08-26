"""
ADK Pipeline Module.
Assembles the 5 specialized LlmAgents into a deterministic ADK SequentialAgent
and configures the InMemoryRunner with full callback-based Observability tracking and ModelConfig.
"""

import logging
from typing import Optional, Tuple
from config import ModelConfig, get_default_model_config
from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner
from agents.breaking_agent import create_breaking_agent
from agents.calendar_agent import create_calendar_agent
from agents.precedent_agent import create_precedent_agent
from agents.safety_agent import create_safety_agent
from agents.synthesis_agent import create_synthesis_agent
from observability.tracker import ObservabilityTracker

logger = logging.getLogger(__name__)


def build_adk_news_pipeline(
    model_config: Optional[ModelConfig] = None,
    model: Optional[str] = None,
    jurisdiction: str = "India",
    app_name: str = "news_intelligence_pipeline",
    tracker: Optional[ObservabilityTracker] = None,
) -> Tuple[SequentialAgent, InMemoryRunner, ObservabilityTracker]:
    """
    Constructs the complete 5-agent ADK Sequential Pipeline with ModelConfig and Thinking levels:
    1. Safety & Triage Agent
    2. Breaking & Fallout Investigator
    3. Precedent & Counter-Narrative Investigator
    4. Forward Calendar & Primary Source Investigator
    5. Synthesis & Neutrality Auditor

    Returns:
        (pipeline_agent, runner, tracker)
    """
    cfg = model_config or get_default_model_config(model_name=model)
    obs_tracker = tracker or ObservabilityTracker(pipeline_name=app_name)

    safety_agent = create_safety_agent(model_config=cfg, jurisdiction=jurisdiction, tracker=obs_tracker)
    breaking_agent = create_breaking_agent(model_config=cfg, tracker=obs_tracker)
    precedent_agent = create_precedent_agent(model_config=cfg, tracker=obs_tracker)
    calendar_agent = create_calendar_agent(model_config=cfg, tracker=obs_tracker)
    synthesis_agent = create_synthesis_agent(model_config=cfg, jurisdiction=jurisdiction, tracker=obs_tracker)

    pipeline_agent = SequentialAgent(
        name="NewsIntelligencePipeline",
        description="Sequential 5-agent pipeline for safety triage, 1-call search investigation, and scenario analysis synthesis.",
        sub_agents=[
            safety_agent,
            breaking_agent,
            precedent_agent,
            calendar_agent,
            synthesis_agent,
        ],
    )

    runner = InMemoryRunner(
        agent=pipeline_agent,
        app_name=app_name,
    )

    return pipeline_agent, runner, obs_tracker
