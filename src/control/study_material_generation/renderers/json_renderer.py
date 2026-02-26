from __future__ import annotations

import json
from pathlib import Path

from ..models import ConceptContentPack


class JsonRenderer:
    def render(self, output_dir: Path, concept_packs: list[ConceptContentPack]) -> dict[str, Path]:
        quiz_payload: list[dict] = []
        flashcard_payload: list[dict] = []
        resources_payload: list[dict] = []

        for pack in concept_packs:
            quiz_payload.append(
                {
                    "concept_id": pack.concept_id,
                    "concept_name": pack.concept_name,
                    "mcqs": pack.mcqs,
                }
            )
            flashcard_payload.append(
                {
                    "concept_id": pack.concept_id,
                    "concept_name": pack.concept_name,
                    "flashcards": pack.flashcards,
                }
            )
            resources_payload.append(
                {
                    "concept_id": pack.concept_id,
                    "concept_name": pack.concept_name,
                    "resources": pack.references,
                }
            )

        quiz_path = output_dir / "quiz.json"
        flashcards_path = output_dir / "flashcards.json"
        resources_path = output_dir / "resources.json"

        quiz_path.write_text(json.dumps(quiz_payload, indent=2), encoding="utf-8")
        flashcards_path.write_text(json.dumps(flashcard_payload, indent=2), encoding="utf-8")
        resources_path.write_text(json.dumps(resources_payload, indent=2), encoding="utf-8")

        return {
            "quiz_json": quiz_path,
            "flashcards_json": flashcards_path,
            "resources_json": resources_path,
        }
