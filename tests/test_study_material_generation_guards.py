from __future__ import annotations

import json
import unittest

from src.config.settings import Settings
from src.control.study_material_generation.agents.quality_guardian_agent import QualityGuardianAgent
from src.control.study_material_generation.agents.worked_example_agent import WorkedExampleAgent
from src.control.study_material_generation.retrieval.models import EvidenceSnippet
from src.control.study_material_generation.retrieval.service import EvidenceRetrievalService


def build_settings() -> Settings:
    return Settings(JWT_SECRET="x" * 16)


class WorkedExampleAgentTests(unittest.TestCase):
    def test_worked_example_agent_disables_provider_json_mode(self) -> None:
        agent = WorkedExampleAgent(build_settings())
        self.assertFalse(agent.enable_json_mode)

    def test_normalize_examples_preserves_structured_payload(self) -> None:
        agent = WorkedExampleAgent(build_settings())
        normalized = agent._normalize_examples(
            [
                {
                    "title": "Worked Derivation 1",
                    "prompt": "Derive the relation for heights and distances.",
                    "steps": [
                        "Start with a right triangle and mark the required height.",
                        "Choose the tangent ratio and substitute the known angle.",
                        "Rearrange to isolate the unknown height.",
                    ],
                    "result": "A verified expression for the required height.",
                    "example_type": "derivation",
                }
            ],
            preferred_style="derivation",
            concept_name="Heights and Distances",
            key_steps=["Use the tangent ratio correctly."],
            formulas=["tan(theta) = opposite / adjacent"],
        )

        self.assertEqual(len(normalized), 1)
        payload = json.loads(normalized[0])
        self.assertEqual(payload["example_type"], "derivation")
        self.assertEqual(len(payload["steps"]), 3)


class QualityGuardianAgentTests(unittest.TestCase):
    def test_evidence_only_issue_is_not_treated_as_blocking(self) -> None:
        self.assertTrue(
            QualityGuardianAgent._is_evidence_only_issue("Topic drift in some evidence snippets")
        )
        self.assertFalse(
            QualityGuardianAgent._is_evidence_only_issue("Unsupported formula in the content draft")
        )


class EvidenceRetrievalServiceTests(unittest.TestCase):
    def test_topic_filter_removes_off_topic_snippets_when_relevant_matches_exist(self) -> None:
        service = EvidenceRetrievalService(build_settings())
        snippets = [
            EvidenceSnippet(
                text="Heights and distances problems use trigonometric ratios to find unknown heights.",
                source_url="https://example.com/heights",
                source_title="Heights and Distances Notes",
                domain="example.com",
                query="math heights and distances explained",
                score=0.91,
            ),
            EvidenceSnippet(
                text="Trigonometric identities such as sin^2(x) + cos^2(x) = 1 are used for simplification.",
                source_url="https://example.com/identities",
                source_title="Trigonometric Identities",
                domain="example.com",
                query="math trigonometric identities explained",
                score=0.95,
            ),
        ]

        filtered = service._filter_snippets_for_topic(
            snippets,
            concept_name="Heights and Distances",
            concept_description="Finding inaccessible heights and horizontal distances using trigonometry.",
        )

        self.assertEqual(len(filtered), 1)
        self.assertIn("Heights and Distances", filtered[0].source_title)


if __name__ == "__main__":
    unittest.main()
