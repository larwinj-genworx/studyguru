from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings
from src.core.services import flashcard_service
from src.schemas.study_material import ConceptContentPack


class ArtifactSpecAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="ArtifactSpecAgent",
            goal="Create final renderer-ready concept material schema.",
            backstory="Structured content formatter for study artifacts.",
        )

    def execute(
        self,
        *,
        concept_id: str,
        concept_name: str,
        content: dict[str, Any],
        resource_required: bool = True,
    ) -> ConceptContentPack:
        input_references = content.get("references", [])
        if not isinstance(input_references, list):
            input_references = []
        prompt = (
            f"Concept ID: {concept_id}\n"
            f"Concept: {concept_name}\n"
            f"Content Inputs: {content}\n\n"
            "Return final JSON with keys: definition, intuition, formulas, stepwise_breakdown_required, key_steps, common_mistakes, "
            "examples, mcqs, flashcards, references, recap. "
            "If Content Inputs.examples already contains structured worked-example payloads, preserve that structure instead of rewriting them into generic summary sentences. "
            "Preserve stepwise_breakdown_required from Content Inputs. If it is false, keep key_steps as an empty list instead of forcing a process section. "
            "Use empty lists where needed. "
            "Strict rule: final output must be coherent and fully bound to this concept. "
            "Do not invent or add references; use exactly the references provided in Content Inputs. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(prompt)

        definition = str(data.get("definition") or content.get("definition") or "").strip()
        intuition = str(data.get("intuition") or content.get("intuition") or "").strip()
        formulas = self.to_list(data.get("formulas"), self.to_list(content.get("formulas"), []))
        stepwise_breakdown_required = self._to_bool(
            data.get("stepwise_breakdown_required", content.get("stepwise_breakdown_required")),
            default=bool(content.get("stepwise_breakdown_required", False)),
        )
        key_steps = self.to_list(data.get("key_steps"), self.to_list(content.get("key_steps"), []))[:8]
        if not stepwise_breakdown_required:
            key_steps = []
        common_mistakes = self.to_list(
            data.get("common_mistakes"),
            self.to_list(content.get("common_mistakes"), []),
        )[:6]
        source_examples = self.to_list(content.get("examples"), [])
        generated_examples = self.to_list(data.get("examples"), [])
        examples = (source_examples or generated_examples)[:5]
        recap = self.to_list(data.get("recap"), self.to_list(content.get("recap"), []))[:8]
        if not definition or not intuition or not common_mistakes or not recap:
            raise ValueError("ArtifactSpecAgent produced incomplete concept payload.")
        practical_required = bool(content.get("practical_examples_required", True))
        if practical_required and not examples:
            raise ValueError("ArtifactSpecAgent produced insufficient examples for this concept.")

        mcqs = data.get("mcqs")
        if not isinstance(mcqs, list) or len(mcqs) < 6:
            mcqs = content.get("mcqs", [])
        if not isinstance(mcqs, list):
            mcqs = []

        source_flashcards = content.get("flashcards", [])
        if not isinstance(source_flashcards, list):
            source_flashcards = []
        generated_flashcards = data.get("flashcards", [])
        if not isinstance(generated_flashcards, list):
            generated_flashcards = []
        flashcards = flashcard_service.build_flashcards(
            concept_name=concept_name,
            definition=definition,
            intuition=intuition,
            key_steps=key_steps,
            common_mistakes=common_mistakes,
            recap=recap,
            formulas=[str(item).strip() for item in formulas if str(item).strip()],
            raw_flashcards=[
                item
                for item in [*source_flashcards, *generated_flashcards]
                if isinstance(item, dict)
            ],
        )
        references = input_references
        if len(mcqs) < 6 or len(flashcards) < 8:
            raise ValueError("ArtifactSpecAgent produced insufficient practice coverage.")
        if resource_required and len(references) < 1:
            raise ValueError("ArtifactSpecAgent produced insufficient resource coverage.")

        return ConceptContentPack(
            concept_id=concept_id,
            concept_name=concept_name,
            definition=definition,
            intuition=intuition,
            stepwise_breakdown_required=stepwise_breakdown_required,
            formulas=[str(item).strip() for item in formulas if str(item).strip()][:6],
            key_steps=key_steps,
            common_mistakes=common_mistakes,
            examples=examples,
            mcqs=mcqs[:10],
            flashcards=flashcards[:15],
            references=references[:8],
            recap=recap,
            practical_examples_required=practical_required,
        )

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "required"}:
                return True
            if normalized in {"false", "no", "0", "not required"}:
                return False
        return default
