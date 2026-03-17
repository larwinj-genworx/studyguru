from __future__ import annotations

import re
from typing import Any


_DEFAULT_HINTS = {
    "core": "Recall the exact meaning of this idea before you flip.",
    "intuition": "Bring back the intuitive picture behind the concept.",
    "step": "Recall what must happen at this stage.",
    "formula": "Bring back the exact relation or equation used here.",
    "pitfall": "Remember the mistake students usually make here.",
    "summary": "Summarize this takeaway in full before checking.",
    "practice": "Recall the correct way to practice or verify this topic.",
    "concept": "Use this cue to recall the full concept precisely.",
}

_HEADING_FALLBACKS = {
    "core": "Core Idea",
    "intuition": "Concept Insight",
    "step": "Key Step",
    "formula": "Key Formula",
    "pitfall": "Common Pitfall",
    "summary": "Quick Recall",
    "practice": "Practice Pattern",
    "concept": "Key Recall",
}

_INTERROGATIVE_PREFIXES = (
    "what ",
    "why ",
    "how ",
    "when ",
    "which ",
    "who ",
    "where ",
)

_VAGUE_FLASHCARD_LABELS = {
    "core idea",
    "concept insight",
    "key step",
    "key formula",
    "common pitfall",
    "quick recall",
    "practice pattern",
    "method",
    "intuition",
    "verification",
    "why it matters",
    "core importance",
}

_HEADING_VERB_PREFIXES = (
    "absorb",
    "take",
    "use",
    "release",
    "convert",
    "identify",
    "check",
    "verify",
    "apply",
    "choose",
    "rearrange",
    "simplify",
    "substitute",
    "derive",
    "calculate",
    "find",
    "measure",
    "compare",
    "explain",
    "remember",
    "recall",
    "confusing",
    "forgetting",
    "skipping",
    "missing",
    "avoiding",
)

_ACTION_NOUNS = {
    "absorb": "Absorption",
    "take in": "Intake",
    "take": "Intake",
    "use": "Use",
    "release": "Release",
    "convert": "Conversion",
    "identify": "Identification",
    "check": "Check",
    "verify": "Verification",
    "apply": "Application",
    "choose": "Selection",
    "rearrange": "Rearrangement",
    "simplify": "Simplification",
    "substitute": "Substitution",
    "derive": "Derivation",
    "calculate": "Calculation",
    "find": "Finding",
    "measure": "Measurement",
    "compare": "Comparison",
}


def build_flashcards(
    *,
    concept_name: str,
    definition: str = "",
    intuition: str = "",
    key_steps: list[str] | None = None,
    common_mistakes: list[str] | None = None,
    recap: list[str] | None = None,
    formulas: list[str] | None = None,
    raw_flashcards: list[dict[str, Any]] | None = None,
    max_cards: int = 15,
) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    cards.extend(_normalize_raw_cards(raw_flashcards or [], concept_name=concept_name))
    cards.extend(
        _build_structured_cards(
            concept_name=concept_name,
            definition=definition,
            intuition=intuition,
            key_steps=key_steps or [],
            common_mistakes=common_mistakes or [],
            recap=recap or [],
            formulas=formulas or [],
        )
    )
    cards.extend(_build_fallback_cards(concept_name))
    return _dedupe_cards(cards)[:max_cards]


def normalize_flashcards(
    *,
    concept_name: str,
    raw_flashcards: list[dict[str, Any]] | None,
    max_cards: int = 15,
    allow_fallback: bool = False,
) -> list[dict[str, str]]:
    cards = _normalize_raw_cards(raw_flashcards or [], concept_name=concept_name)
    if not cards and allow_fallback:
        cards = _build_fallback_cards(concept_name)
    return _dedupe_cards(cards)[:max_cards]


def _build_structured_cards(
    *,
    concept_name: str,
    definition: str,
    intuition: str,
    key_steps: list[str],
    common_mistakes: list[str],
    recap: list[str],
    formulas: list[str],
) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []

    if _clean_text(definition):
        cards.append(
            {
                "question": f"What is {concept_name}?",
                "hint": _DEFAULT_HINTS["core"],
                "answer": _compact_answer(definition, max_sentences=2),
                "kind": "core",
            }
        )

    if _clean_text(intuition):
        cards.append(
            {
                "question": f"Why does {concept_name} make sense?",
                "hint": _DEFAULT_HINTS["intuition"],
                "answer": _compact_answer(intuition, max_sentences=2),
                "kind": "intuition",
            }
        )

    for index, step in enumerate(key_steps[:5], start=1):
        cleaned = _clean_text(step)
        if not cleaned:
            continue
        cards.append(
            {
                "question": _question_from_step(cleaned, concept_name=concept_name, index=index),
                "hint": _DEFAULT_HINTS["step"],
                "answer": _compact_answer(cleaned, max_sentences=2),
                "kind": "step",
            }
        )

    for index, formula in enumerate(formulas[:2], start=1):
        cleaned = _clean_text(formula)
        if not cleaned:
            continue
        cards.append(
            {
                "question": _formula_question(cleaned, concept_name=concept_name, index=index),
                "hint": _DEFAULT_HINTS["formula"],
                "answer": cleaned,
                "kind": "formula",
            }
        )

    for index, mistake in enumerate(common_mistakes[:3], start=1):
        cleaned = _clean_text(mistake)
        if not cleaned:
            continue
        cards.append(
            {
                "question": _question_from_pitfall(cleaned, concept_name=concept_name, index=index),
                "hint": _DEFAULT_HINTS["pitfall"],
                "answer": _compact_answer(cleaned, max_sentences=2),
                "kind": "pitfall",
            }
        )

    for index, point in enumerate(recap[:3], start=1):
        cleaned = _clean_text(point)
        if not cleaned:
            continue
        cards.append(
            {
                "question": _question_from_summary(cleaned, concept_name=concept_name, index=index),
                "hint": _DEFAULT_HINTS["summary"],
                "answer": _compact_answer(cleaned, max_sentences=2),
                "kind": "summary",
            }
        )

    return cards


def _normalize_raw_cards(
    raw_flashcards: list[dict[str, Any]],
    *,
    concept_name: str,
) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for index, item in enumerate(raw_flashcards, start=1):
        if not isinstance(item, dict):
            continue
        answer = _compact_answer(str(item.get("answer", "")), max_sentences=2)
        if not answer:
            continue
        raw_question = _clean_text(str(item.get("question", "")))
        kind = _normalize_kind(str(item.get("kind", "")), raw_question)
        hint = _clean_text(str(item.get("hint", ""))) or _DEFAULT_HINTS[kind]
        cards.append(
            {
                "question": _normalize_question(
                    raw_question=raw_question,
                    kind=kind,
                    index=index,
                    concept_name=concept_name,
                    answer=answer,
                ),
                "hint": hint,
                "answer": answer,
                "kind": kind,
            }
        )
    return cards


def _build_fallback_cards(concept_name: str) -> list[dict[str, str]]:
    return [
        {
            "question": f"What is {concept_name}?",
            "hint": _DEFAULT_HINTS["core"],
            "answer": f"{concept_name} is a foundational topic that students should be able to explain clearly and apply with confidence.",
            "kind": "core",
        },
        {
            "question": f"Why is {concept_name} important?",
            "hint": _DEFAULT_HINTS["summary"],
            "answer": "The topic builds understanding that supports later steps, applications, and accuracy checks.",
            "kind": "summary",
        },
        {
            "question": f"What intuitive idea helps explain {concept_name}?",
            "hint": _DEFAULT_HINTS["intuition"],
            "answer": f"Think of {concept_name} as an idea that becomes easier when the rule and the reason behind it are both remembered.",
            "kind": "intuition",
        },
        {
            "question": f"Which step should you identify first in {concept_name}?",
            "hint": _DEFAULT_HINTS["step"],
            "answer": "Start by identifying the rule or relationship that controls the concept before solving further.",
            "kind": "step",
        },
        {
            "question": f"What should you verify after applying {concept_name}?",
            "hint": _DEFAULT_HINTS["practice"],
            "answer": "After solving, check that the method, units, and final result stay consistent with the concept.",
            "kind": "practice",
        },
        {
            "question": f"What common mistake should you avoid in {concept_name}?",
            "hint": _DEFAULT_HINTS["pitfall"],
            "answer": "Students often skip an intermediate step or use the right idea in the wrong order.",
            "kind": "pitfall",
        },
        {
            "question": f"How should you revise {concept_name} effectively?",
            "hint": _DEFAULT_HINTS["practice"],
            "answer": "Revise by recalling the definition, the main steps, and one solved example instead of only rereading notes.",
            "kind": "practice",
        },
        {
            "question": f"What is the quickest high-value review pattern for {concept_name}?",
            "hint": _DEFAULT_HINTS["summary"],
            "answer": "Strong recall comes from short, repeated review of the core meaning, process, and common mistake.",
            "kind": "summary",
        },
    ]


def _normalize_kind(raw_kind: str, question: str) -> str:
    normalized = _clean_text(raw_kind).lower()
    if normalized in _DEFAULT_HINTS:
        return normalized

    question_text = question.lower()
    if question_text in {"core idea", "definition", "main idea"}:
        return "core"
    if question_text in {"intuition", "concept insight"}:
        return "intuition"
    if question_text in {"quick recall", "core importance", "why it matters"}:
        return "summary"
    if question_text in {"method", "key step"}:
        return "step"
    if question_text in {"common pitfall"}:
        return "pitfall"
    if question_text in {"practice pattern", "verification"}:
        return "practice"
    if "mistake" in question_text or "pitfall" in question_text or "avoid" in question_text:
        return "pitfall"
    if "formula" in question_text or "equation" in question_text or "relation" in question_text:
        return "formula"
    if "practice" in question_text or "check" in question_text or "verify" in question_text:
        return "practice"
    if question_text.startswith("why "):
        return "summary"
    if question_text.startswith("how ") and ("step" in question_text or "process" in question_text):
        return "step"
    if question_text.startswith("what is ") or question_text.startswith("define "):
        return "core"
    return "concept"


def _normalize_question(
    *,
    raw_question: str,
    kind: str,
    index: int,
    concept_name: str,
    answer: str,
) -> str:
    cleaned = raw_question.strip()
    if _is_question_candidate(cleaned) and not _is_question_too_close_to_answer(cleaned, answer):
        return _ensure_question(cleaned)

    if cleaned:
        derived_from_question = _question_from_heading(
            cleaned,
            kind=kind,
            concept_name=concept_name,
            index=index,
        )
        if derived_from_question and not _is_question_too_close_to_answer(derived_from_question, answer):
            return derived_from_question

    return _question_from_heading(
        answer,
        kind=kind,
        concept_name=concept_name,
        index=index,
    )


def _question_from_heading(
    text: str,
    *,
    kind: str,
    concept_name: str,
    index: int,
) -> str:
    cleaned = _clean_text(text).rstrip("?").strip()
    if kind == "core":
        return f"What is {concept_name}?"
    if kind == "intuition":
        return f"Why does {concept_name} make sense?"
    if kind == "formula":
        return _formula_question(cleaned, concept_name=concept_name, index=index)
    if kind == "pitfall":
        return _question_from_pitfall(cleaned, concept_name=concept_name, index=index)
    if kind == "summary":
        return _question_from_summary(cleaned, concept_name=concept_name, index=index)
    if kind == "practice":
        return _question_from_practice(cleaned, concept_name=concept_name, index=index)
    if kind == "step":
        return _question_from_step(cleaned, concept_name=concept_name, index=index)
    return _question_from_concept(cleaned, concept_name=concept_name, index=index)


def _question_from_step(text: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return f"Which step matters most in {concept_name}?"

    lowered = cleaned.lower()
    step_match = re.match(r"^(?:step\s+\d+[:.\-]?\s*)?(first|next|then|finally)\s+(.+)$", lowered)
    if step_match:
        stage = step_match.group(1)
        if stage == "then":
            stage = "next"
        return _ensure_question(f"What happens {stage} in {concept_name}")
    if lowered.startswith(("check ", "verify ")):
        return _ensure_question(f"What should you check in {concept_name}")
    return _ensure_question(f"What is step {index} in {concept_name}")


def _question_from_pitfall(text: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return f"What common mistake should you avoid in {concept_name}?"
    if re.search(r"\b(confusing|mixing)\b", cleaned, flags=re.IGNORECASE):
        return _ensure_question(f"Which ideas are commonly confused in {concept_name}?")
    if re.search(r"\b(skip|skipping|miss|missing|forget|forgetting|ignore|ignoring)\b", cleaned, flags=re.IGNORECASE):
        return _ensure_question(f"What important check is often missed in {concept_name}?")
    return _ensure_question(f"What common mistake should you avoid in {concept_name}?")


def _question_from_summary(text: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return f"What is the main takeaway from {concept_name}?"
    if re.search(r"\bimportant|matters|helps|used\b", cleaned, flags=re.IGNORECASE):
        return _ensure_question(f"Why does {concept_name} matter?")
    return _ensure_question(f"What is a key takeaway from {concept_name}?")


def _question_from_practice(text: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return f"How should you practice {concept_name}?"
    if re.search(r"\b(check|verify|verification)\b", cleaned, flags=re.IGNORECASE):
        return _ensure_question(f"What should you verify after applying {concept_name}?")
    return _ensure_question(f"How should you practice {concept_name}?")


def _question_from_concept(text: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return f"What should you remember about {concept_name}?"
    lowered = cleaned.lower()
    if lowered not in _VAGUE_FLASHCARD_LABELS and len(cleaned.split()) <= 5 and not re.search(r"[.:,;]", cleaned):
        return _ensure_question(f"What is {cleaned}")
    if re.search(r"\bwhy\b", cleaned, flags=re.IGNORECASE):
        return _ensure_question(f"Why is {concept_name} used?")
    return _ensure_question(f"What should you remember about {concept_name}?")


def _formula_question(formula: str, *, concept_name: str, index: int) -> str:
    cleaned = _clean_text(formula)
    if not cleaned:
        return f"Which formula is used in {concept_name}?"
    left, _, _ = cleaned.partition("=")
    left = left.strip()
    if left and len(left) <= 18:
        return _ensure_question(f"What is the formula for {left}?")
    return _ensure_question(f"Which formula is used in {concept_name}?")


def _is_question_candidate(value: str) -> bool:
    cleaned = _clean_text(value)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    return cleaned.endswith("?") or any(lowered.startswith(prefix) for prefix in _INTERROGATIVE_PREFIXES)


def _ensure_question(value: str) -> str:
    cleaned = _clean_text(value).rstrip("?").strip()
    if not cleaned:
        return "What should you remember?"
    return f"{cleaned}?"


def _is_question_too_close_to_answer(question: str, answer: str) -> bool:
    question_key = _normalize_key(question.rstrip("?"))
    answer_key = _normalize_key(answer)
    if not question_key or not answer_key:
        return False
    if question_key == answer_key:
        return True
    if len(question_key.split()) >= 4 and answer_key.startswith(question_key):
        return True
    return False


def _formula_heading(formula: str, index: int) -> str:
    lowered = formula.lower()
    if "tan(" in lowered or lowered.startswith("tan ") or " tan " in lowered:
        return "Tangent Ratio"
    if "sin(" in lowered or lowered.startswith("sin ") or " sin " in lowered:
        return "Sine Ratio"
    if "cos(" in lowered or lowered.startswith("cos ") or " cos " in lowered:
        return "Cosine Ratio"
    left, _, _ = formula.partition("=")
    cleaned = left.strip()
    if cleaned and len(cleaned) <= 18:
        return f"Formula for {cleaned}"
    return f"Formula {index}"


def _compact_answer(text: str, *, max_sentences: int, max_chars: int = 260) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", cleaned)
    if sentences:
        limited = " ".join(sentence.strip() for sentence in sentences[:max_sentences]).strip()
    else:
        limited = cleaned
    if len(limited) <= max_chars:
        return limited
    shortened = limited[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{shortened}..." if shortened else limited[:max_chars].strip()


def _dedupe_cards(cards: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_questions: set[str] = set()
    seen_answers: set[str] = set()
    for card in cards:
        question = _clean_text(card.get("question", ""))
        answer = _clean_text(card.get("answer", ""))
        hint = _clean_text(card.get("hint", ""))
        kind = _clean_text(card.get("kind", "concept")).lower() or "concept"
        if not question or not answer:
            continue
        question_key = _normalize_key(question)
        answer_key = _normalize_key(answer)
        if question_key in seen_questions or answer_key in seen_answers:
            continue
        seen_questions.add(question_key)
        seen_answers.add(answer_key)
        deduped.append(
            {
                "question": question,
                "hint": hint or _DEFAULT_HINTS.get(kind, _DEFAULT_HINTS["concept"]),
                "answer": answer,
                "kind": kind if kind in _DEFAULT_HINTS else "concept",
            }
        )
    return deduped


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _clean_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    return cleaned.strip(" -")


def _is_heading_candidate(value: str) -> bool:
    cleaned = _clean_text(value).rstrip(".")
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix) for prefix in _INTERROGATIVE_PREFIXES):
        return False
    if len(cleaned.split()) > 5:
        return False
    first_word = lowered.split(" ", 1)[0]
    if first_word in _HEADING_VERB_PREFIXES:
        return False
    if re.search(r"[.!?]", cleaned):
        return False
    return True


def _is_heading_too_close_to_answer(question: str, answer: str) -> bool:
    question_key = _normalize_key(question)
    answer_key = _normalize_key(answer)
    if not question_key or not answer_key:
        return False
    if question_key == answer_key:
        return True
    if len(question_key.split()) >= 3 and answer_key.startswith(question_key):
        return True
    return False


def _derive_heading_from_text(
    text: str,
    *,
    kind: str,
    concept_name: str,
    index: int,
) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return concept_name if kind == "core" else _HEADING_FALLBACKS.get(kind, "Key Recall")
    if kind == "core":
        return concept_name
    if kind == "formula":
        return _formula_heading(cleaned, index)
    if kind == "intuition":
        return f"{concept_name} Intuition"

    if kind == "pitfall":
        return _pitfall_heading(cleaned, index)
    if kind == "summary":
        return _summary_heading(cleaned, index)
    if kind == "practice":
        return _practice_heading(cleaned, index)
    if kind == "step":
        return _action_heading(cleaned, fallback=f"Key Step {index}")
    return _action_heading(cleaned, fallback=f"Key Recall {index}")


def _pitfall_heading(text: str, index: int) -> str:
    comparison_match = re.match(
        r"^(?:confusing|mixing)\s+(.+?)\s+with\s+(.+?)(?:[.,]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if comparison_match:
        left = _smart_title(_trim_phrase(comparison_match.group(1)))
        right = _smart_title(_trim_phrase(comparison_match.group(2)))
        if left and right:
            return f"{left} vs {right}"

    required_match = re.match(
        r"^(?:forgetting that|missing)\s+(.+?)\s+is\s+required(?:[.,]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if required_match:
        topic = _smart_title(_trim_phrase(required_match.group(1)))
        if topic:
            return f"{topic} Requirement"

    skipping_match = re.match(r"^(?:skipping|ignoring|not checking)\s+(.+?)(?:[.,]|$)", text, flags=re.IGNORECASE)
    if skipping_match:
        topic = _smart_title(_trim_phrase(skipping_match.group(1)))
        if topic:
            return topic

    return _action_heading(text, fallback=f"Common Pitfall {index}")


def _summary_heading(text: str, index: int) -> str:
    relation_match = re.match(r"^(?:the\s+)?(.+?)\s+(?:is|are)\s+(.+?)(?:[.,]|$)", text, flags=re.IGNORECASE)
    if relation_match:
        left = _smart_title(_trim_phrase(relation_match.group(1)))
        if left:
            return left

    conversion_match = re.search(r"(.+?)\s+into\s+(.+?)(?:[.,]|$)", text, flags=re.IGNORECASE)
    if conversion_match:
        right = conversion_match.group(2).strip().lower()
        if "energy" in right or "energy" in text.lower():
            return "Energy Conversion"

    return _action_heading(text, fallback=f"Key Takeaway {index}")


def _practice_heading(text: str, index: int) -> str:
    verification_match = re.search(r"\b(check|verify|verification)\b", text, flags=re.IGNORECASE)
    if verification_match:
        return "Verification"
    revision_match = re.search(r"\b(practice|revise|revision|recall)\b", text, flags=re.IGNORECASE)
    if revision_match:
        return "Practice Pattern"
    return _action_heading(text, fallback=f"Practice Focus {index}")


def _action_heading(text: str, *, fallback: str) -> str:
    action_match = re.match(
        r"^(take in|take|absorbs?|uses?|releases?|converts?|identify|identifies|checks?|verify|verifies|apply|applies|choose|chooses|rearranges?|simplify|simplifies|substitutes?|derives?|calculates?|finds?|measures?|compares?)\s+(.+?)(?:\s+(?:using|with|from|through|into|to|by|for|after|before|when|as|and)\b|[.,]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if action_match:
        verb = _normalize_action_verb(action_match.group(1))
        target = _smart_title(_trim_phrase(action_match.group(2)))
        noun = _ACTION_NOUNS.get(verb, "")
        if target and noun:
            return f"{target} {noun}"

    relation_match = re.match(r"^(?:the\s+)?(.+?)\s+(?:is|are)\s+(.+?)(?:[.,]|$)", text, flags=re.IGNORECASE)
    if relation_match:
        left = _smart_title(_trim_phrase(relation_match.group(1)))
        if left:
            return left

    phrase = _trim_phrase(text)
    shortened = _smart_title(" ".join(phrase.split()[:3]))
    return shortened or fallback


def _trim_phrase(value: str) -> str:
    cleaned = _clean_text(value)
    cleaned = re.sub(r"^(?:the|a|an|this|that)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _smart_title(value: str) -> str:
    words = [word for word in value.split() if word]
    normalized: list[str] = []
    for word in words[:4]:
        if re.fullmatch(r"[a-z]+", word):
            normalized.append(word.capitalize())
        else:
            normalized.append(word)
    return " ".join(normalized).strip()


def _normalize_action_verb(value: str) -> str:
    verb = value.lower().strip()
    explicit = {
        "takes": "take",
        "absorbs": "absorb",
        "uses": "use",
        "releases": "release",
        "converts": "convert",
        "identifies": "identify",
        "checks": "check",
        "verifies": "verify",
        "applies": "apply",
        "chooses": "choose",
        "rearranges": "rearrange",
        "simplifies": "simplify",
        "substitutes": "substitute",
        "derives": "derive",
        "calculates": "calculate",
        "finds": "find",
        "measures": "measure",
        "compares": "compare",
    }
    if verb in explicit:
        return explicit[verb]
    if verb in {"takes", "take"}:
        return "take"
    if verb == "take in":
        return "take in"
    return verb
