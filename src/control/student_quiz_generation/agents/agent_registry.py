from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import Settings
from .quiz_item_agent import QuizItemAgent


@dataclass(frozen=True)
class QuizAgentRegistry:
    quiz_item: QuizItemAgent


def build_agent_registry(settings: Settings) -> QuizAgentRegistry:
    return QuizAgentRegistry(quiz_item=QuizItemAgent(settings))
