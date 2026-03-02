from __future__ import annotations

import re
from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class FormulaExplainerAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="FormulaExplainerAgent",
            goal="Explain formulas with clear variable descriptions.",
            backstory="Math-aware tutor who clarifies variables and usage.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        grade_level: str,
        formulas: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        cleaned_formulas = [str(item).strip() for item in formulas if str(item).strip()]
        if not cleaned_formulas:
            return {"formula_cards": []}

        prompt = (
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Formulas: {cleaned_formulas}\n\n"
            "Return JSON with key: formula_cards (list). "
            "Each item must include: formula (string), variables (list of {symbol, meaning}), "
            "explanation (string, 1-2 sentences), example (string, optional). "
            "Keep variable meanings concise and aligned to the concept. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(prompt, required_keys=["formula_cards"])
        cards = data.get("formula_cards")
        if not isinstance(cards, list):
            cards = []

        normalized: list[dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            formula = str(card.get("formula", "")).strip()
            if not formula:
                continue
            variables = card.get("variables") or []
            cleaned_vars = []
            for var in variables:
                if not isinstance(var, dict):
                    continue
                symbol = str(var.get("symbol", "")).strip()
                meaning = str(var.get("meaning", "")).strip()
                if symbol and meaning:
                    cleaned_vars.append({"symbol": symbol, "meaning": meaning})
            normalized.append(
                {
                    "formula": formula,
                    "variables": cleaned_vars,
                    "explanation": str(card.get("explanation", "")).strip(),
                    "example": str(card.get("example", "")).strip(),
                }
            )

        if not normalized:
            normalized = self._fallback_cards(cleaned_formulas)
        return {"formula_cards": normalized}

    @staticmethod
    def _fallback_cards(formulas: list[str]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for formula in formulas:
            variables = [
                {"symbol": symbol, "meaning": "Variable in the formula"}
                for symbol in FormulaExplainerAgent._extract_variables(formula)
            ]
            cards.append(
                {
                    "formula": formula,
                    "variables": variables,
                    "explanation": "",
                    "example": "",
                }
            )
        return cards

    @staticmethod
    def _extract_variables(formula: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", formula)
        ignore = {"sin", "cos", "tan", "log", "ln", "sqrt"}
        cleaned: list[str] = []
        for token in tokens:
            if token.lower() in ignore:
                continue
            if token not in cleaned:
                cleaned.append(token)
        return cleaned[:8]
