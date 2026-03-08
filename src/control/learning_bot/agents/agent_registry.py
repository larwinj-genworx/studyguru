from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import Settings

from .learning_bot_response_agent import LearningBotResponseAgent


@dataclass(slots=True)
class LearningBotAgentRegistry:
    response: LearningBotResponseAgent


def build_agent_registry(settings: Settings) -> LearningBotAgentRegistry:
    return LearningBotAgentRegistry(response=LearningBotResponseAgent(settings))
