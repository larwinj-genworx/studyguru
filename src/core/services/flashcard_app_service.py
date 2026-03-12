from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from src.core.services import flashcard_service, material_job_service
from src.core.services.object_storage_service import get_object_storage_service
from src.data.repositories import material_job_repository, study_material_repository
from src.schemas.study_material import FlashcardItem, MaterialLifecycleStatus

_storage = get_object_storage_service()


def _load_flashcard_payload(path: Path, concept_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stored flashcards could not be read: {exc}",
        ) from exc

    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict) or entry.get("concept_id") != concept_id:
                continue
            raw_flashcards = entry.get("flashcards", [])
            return raw_flashcards if isinstance(raw_flashcards, list) else []
        return []

    if isinstance(payload, dict):
        raw_flashcards = payload.get("flashcards", [])
        return raw_flashcards if isinstance(raw_flashcards, list) else []

    return []


async def get_student_concept_flashcards(
    subject_id: str,
    concept_id: str,
) -> list[FlashcardItem]:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")

    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")

    material = await study_material_repository.get_latest_material(concept_id, published_only=True)
    if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published concept material not found.")

    job = await material_job_repository.get_job(material.source_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")

    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    relative_path = material_job_service.resolve_published_concept_artifact_relative_path(
        record,
        concept_id,
        "flashcards_json",
    )
    flashcard_path = _storage.ensure_local_copy(
        _storage.material_area,
        relative_path,
    )
    raw_flashcards = _load_flashcard_payload(flashcard_path, concept_id)
    normalized = flashcard_service.normalize_flashcards(
        concept_name=concept.name,
        raw_flashcards=raw_flashcards,
    )
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcards are not available for this concept.",
        )
    return [FlashcardItem(**item) for item in normalized]
