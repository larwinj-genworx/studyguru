from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.settings import Settings
from src.schemas.quiz import (
    QuizQuestionResponse,
    QuizReportResponse,
    QuizSessionResponse,
    QuizTopicPerformance,
    QuizTopicSummary,
)
from src.schemas.study_material import LearningContent


@dataclass(frozen=True)
class ConceptProfile:
    concept_id: str
    concept_name: str
    complexity_score: float
    required_depth: str | None
    material_version: int
    content: LearningContent


def compute_complexity_score(metadata: dict[str, Any]) -> float:
    raw = metadata.get("complexity_score")
    if raw is not None:
        try:
            value = float(raw)
            return max(0.0, min(1.0, value))
        except Exception:
            pass
    level = str(metadata.get("concept_level") or "").strip().lower()
    if level == "micro":
        return 0.3
    if level == "mid":
        return 0.6
    if level == "macro":
        return 0.85
    return 0.5


def compute_required_depth(metadata: dict[str, Any]) -> str | None:
    depth = str(metadata.get("required_depth") or "").strip().lower()
    return depth if depth else None


def compute_target_question_count(
    *,
    concepts: list[ConceptProfile],
    settings: Settings,
) -> int:
    if not concepts:
        return 0
    base = settings.quiz_base_questions + settings.quiz_per_topic_questions * len(concepts)
    avg_complexity = sum(profile.complexity_score for profile in concepts) / len(concepts)
    multiplier = 1 + settings.quiz_complexity_multiplier * avg_complexity
    target = round(base * multiplier)
    return int(max(settings.quiz_min_questions, min(settings.quiz_max_questions, target)))


def compute_topic_weights(concepts: list[ConceptProfile]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for profile in concepts:
        weight = 0.6 + profile.complexity_score
        if profile.required_depth == "deep":
            weight += 0.15
        elif profile.required_depth == "basic":
            weight -= 0.05
        weights[profile.concept_id] = max(0.2, weight)
    return weights


def allocate_question_counts(
    *,
    total_questions: int,
    concepts: list[ConceptProfile],
    weights: dict[str, float],
) -> dict[str, int]:
    if not concepts or total_questions <= 0:
        return {}
    concept_ids = [profile.concept_id for profile in concepts]
    if total_questions < len(concept_ids):
        sorted_ids = sorted(concept_ids, key=lambda cid: weights.get(cid, 1.0), reverse=True)
        return {cid: 1 if idx < total_questions else 0 for idx, cid in enumerate(sorted_ids)}

    total_weight = sum(weights.get(cid, 1.0) for cid in concept_ids)
    raw_allocations = {
        cid: (weights.get(cid, 1.0) / total_weight) * total_questions for cid in concept_ids
    }
    counts = {cid: max(1, int(raw)) for cid, raw in raw_allocations.items()}
    allocated = sum(counts.values())
    if allocated == total_questions:
        return counts

    remainder = total_questions - allocated
    if remainder > 0:
        fractional = sorted(
            concept_ids,
            key=lambda cid: raw_allocations[cid] - int(raw_allocations[cid]),
            reverse=True,
        )
        for cid in fractional:
            if remainder <= 0:
                break
            counts[cid] += 1
            remainder -= 1
    else:
        surplus_ids = sorted(
            concept_ids,
            key=lambda cid: raw_allocations[cid] - int(raw_allocations[cid]),
        )
        for cid in surplus_ids:
            if remainder >= 0:
                break
            if counts[cid] > 1:
                counts[cid] -= 1
                remainder += 1
    return counts


def extract_quiz_context(content: LearningContent) -> dict[str, Any]:
    overview = _extract_overview(content)
    key_points = _extract_list_items(content, target_titles={"core concepts"})
    quick_revision = _extract_list_items(content, target_titles={"quick revision"})
    common_mistakes = _extract_callout_items(content, target_titles={"common mistakes", "watch out for"})
    highlights = [item for item in (content.highlights or []) if str(item).strip()]

    summary_parts = [overview, *highlights[:4]]
    summary = " ".join([part for part in summary_parts if part]).strip()
    if not summary:
        summary = "Review the core definition, key steps, and typical mistakes for this concept."

    if not key_points:
        key_points = highlights[:6]
    if not common_mistakes:
        common_mistakes = ["Avoid rushing; verify each step with the definition."]

    return {
        "summary": summary[:900],
        "key_points": [item for item in key_points if item][:8],
        "common_mistakes": [item for item in common_mistakes if item][:6],
        "quick_revision": [item for item in quick_revision if item][:6],
    }


def sanitize_hints(
    *,
    hints: list[str],
    answer: str,
    concept_name: str,
    question: str,
) -> list[str]:
    normalized_answer = answer.strip().lower()
    cleaned: list[str] = []
    for hint in hints:
        text = str(hint).strip()
        if not text:
            continue
        if normalized_answer and normalized_answer in text.lower():
            continue
        cleaned.append(text)
    fallback = _fallback_hints(concept_name=concept_name, question=question)
    for hint in fallback:
        if len(cleaned) >= 3:
            break
        cleaned.append(hint)
    return cleaned[:3]


def build_quiz_question_response(
    *,
    question_id: str,
    concept_id: str,
    concept_name: str,
    question: str,
    options: list[str],
    difficulty: str,
    position: int,
    total: int,
) -> QuizQuestionResponse:
    return QuizQuestionResponse(
        question_id=question_id,
        concept_id=concept_id,
        concept_name=concept_name,
        question=question,
        options=options,
        difficulty=difficulty,
        position=position,
        total=total,
    )


def build_session_response(
    *,
    session_id: str,
    subject_id: str,
    subject_name: str,
    status: str,
    total_questions: int,
    current_index: int,
    correct_count: int,
    incorrect_count: int,
    first_attempt_correct_count: int,
    started_at: Any,
    completed_at: Any,
    topics: list[QuizTopicSummary],
) -> QuizSessionResponse:
    return QuizSessionResponse(
        session_id=session_id,
        subject_id=subject_id,
        subject_name=subject_name,
        status=status,
        total_questions=total_questions,
        current_index=current_index,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        first_attempt_correct_count=first_attempt_correct_count,
        started_at=started_at,
        completed_at=completed_at,
        topics=topics,
    )


def build_report(
    *,
    session_id: str,
    subject_id: str,
    subject_name: str,
    total_questions: int,
    correct_count: int,
    completed_at: Any,
    topic_performance: list[QuizTopicPerformance],
    metadata: dict[str, Any] | None = None,
) -> QuizReportResponse:
    accuracy = (correct_count / total_questions) if total_questions else 0.0
    recommendations: list[str] = []
    if accuracy < 0.6:
        recommendations.append("Focus on the weakest topics and review their core steps again.")
        recommendations.append("Revisit quick revision notes before the next attempt.")
    elif accuracy < 0.8:
        recommendations.append("Strengthen medium-score topics with 1-2 extra practice sets.")
    else:
        recommendations.append("Great work. Try a harder practice set or apply concepts to real examples.")
    return QuizReportResponse(
        session_id=session_id,
        subject_id=subject_id,
        subject_name=subject_name,
        total_questions=total_questions,
        correct_count=correct_count,
        accuracy=round(accuracy, 3),
        completed_at=completed_at,
        topic_breakdown=topic_performance,
        recommendations=recommendations,
        meta=metadata or {},
    )


def build_topic_performance(
    *,
    concept_id: str,
    concept_name: str,
    correct_count: int,
    total_questions: int,
    highlights: list[str] | None = None,
) -> QuizTopicPerformance:
    accuracy = (correct_count / total_questions) if total_questions else 0.0
    status = "strong"
    if accuracy < 0.6:
        status = "focus"
    elif accuracy < 0.8:
        status = "steady"
    recommendations = _topic_recommendations(concept_name, accuracy, highlights or [])
    return QuizTopicPerformance(
        concept_id=concept_id,
        concept_name=concept_name,
        accuracy=round(accuracy, 3),
        correct_count=correct_count,
        total_questions=total_questions,
        status=status,
        recommendations=recommendations,
    )


def _extract_overview(content: LearningContent) -> str:
    for section in content.sections:
        if section.title.strip().lower() == "overview":
            for block in section.blocks:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    text = str(block.get("text", "")).strip()
                    if text:
                        return text
    return ""


def _extract_list_items(content: LearningContent, target_titles: set[str]) -> list[str]:
    items: list[str] = []
    for section in content.sections:
        if section.title.strip().lower() in target_titles:
            for block in section.blocks:
                if isinstance(block, dict) and block.get("type") == "list":
                    block_items = block.get("items") or []
                    items.extend([str(item).strip() for item in block_items if str(item).strip()])
    return items


def _extract_callout_items(content: LearningContent, target_titles: set[str]) -> list[str]:
    items: list[str] = []
    for section in content.sections:
        title = section.title.strip().lower()
        if title in target_titles:
            for block in section.blocks:
                if isinstance(block, dict) and block.get("type") == "callout":
                    content_items = block.get("content") or []
                    if isinstance(content_items, list):
                        items.extend([str(item).strip() for item in content_items if str(item).strip()])
                    else:
                        text = str(content_items).strip()
                        if text:
                            items.append(text)
    return items


def _fallback_hints(*, concept_name: str, question: str) -> list[str]:
    base = concept_name or "this concept"
    return [
        f"Identify the key term in the question and recall the core definition of {base}.",
        f"Eliminate options that contradict the main rule or step in {base}.",
        f"Match the question to a familiar example of {base} before choosing the option.",
    ]


def _topic_recommendations(concept_name: str, accuracy: float, highlights: list[str]) -> list[str]:
    recommendations: list[str] = []
    if accuracy < 0.6:
        recommendations.append(f"Revisit the Overview and Core Concepts for {concept_name}.")
        recommendations.append("Review common mistakes and try two more practice questions.")
        if highlights:
            recommendations.append(f"Use this key idea as a checkpoint: {highlights[0]}")
    elif accuracy < 0.8:
        recommendations.append(f"Practice one additional set on {concept_name} to improve accuracy.")
        recommendations.append("Focus on steps that cause confusion and verify each choice.")
    else:
        recommendations.append(f"Strong grasp of {concept_name}. Try a harder variant next.")
    return recommendations
