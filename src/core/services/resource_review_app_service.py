from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException, status

from src.core.services import material_job_service
from src.core.services.object_storage_service import get_object_storage_service
from src.core.services.resource_video_service import YouTubeVideoService
from src.data.repositories import material_job_repository, study_material_repository
from src.schemas.study_material import ConceptResourcesResponse, ResourceItem, VideoFeedbackRequest

_storage = get_object_storage_service()
logger = logging.getLogger(__name__)


def _is_youtube_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except (AttributeError, TypeError, ValueError):
        return False
    return "youtube.com" in host or "youtu.be" in host


def _extract_youtube_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except (AttributeError, TypeError, ValueError):
        return None
    host = parsed.hostname or ""
    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        return video_id or None
    if "youtube.com" in host:
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[-1] or None
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[-1] or None
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0] or None
    return None


def _normalize_resource(item: dict[str, Any]) -> ResourceItem | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url", "")).strip()
    if not url:
        return None
    title = str(item.get("title", "Resource")).strip() or "Resource"
    note = item.get("note")
    return ResourceItem(title=title[:120], url=url, note=str(note).strip()[:240] if note else None)


def _load_resources(path: Path, concept_id: str) -> tuple[list[ResourceItem], Any, bool]:
    if not path.exists():
        return [], [], True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("Failed to read stored concept resources.", exc_info=True, extra={"path": str(path)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored concept resources could not be read.",
        ) from exc
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict) and entry.get("concept_id") == concept_id:
                raw_resources = entry.get("resources", [])
                if isinstance(raw_resources, list):
                    resources = [item for item in (_normalize_resource(obj) for obj in raw_resources) if item]
                else:
                    resources = []
                return resources, payload, True
        return [], payload, True
    if isinstance(payload, dict):
        raw_resources = payload.get("resources", [])
        if isinstance(raw_resources, list):
            resources = [item for item in (_normalize_resource(obj) for obj in raw_resources) if item]
        else:
            resources = []
        return resources, payload, False
    return [], [], True


def _write_resources(
    path: Path,
    *,
    concept_id: str,
    concept_name: str,
    resources: list[ResourceItem],
    existing_payload: Any,
    payload_is_list: bool,
) -> None:
    serialized = [item.model_dump(exclude_none=True) for item in resources]
    if payload_is_list:
        payload = existing_payload if isinstance(existing_payload, list) else []
        updated = False
        for entry in payload:
            if isinstance(entry, dict) and entry.get("concept_id") == concept_id:
                entry["resources"] = serialized
                entry["concept_name"] = concept_name
                updated = True
                break
        if not updated:
            payload.append(
                {
                    "concept_id": concept_id,
                    "concept_name": concept_name,
                    "resources": serialized,
                }
            )
    else:
        payload = {
            "concept_id": concept_id,
            "concept_name": concept_name,
            "resources": serialized,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _refresh_zip_bundle(target_dir: Path, zip_name: str = "study_material_bundle.zip") -> Path:
    if not target_dir.exists():
        return target_dir / zip_name
    zip_path = target_dir / zip_name
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for file_path in target_dir.rglob("*"):
            if file_path.is_file() and file_path.name != zip_name:
                zf.write(file_path, arcname=str(file_path.relative_to(target_dir)))
    return zip_path


async def _resolve_concept_resources_path(
    subject_id: str,
    concept_id: str,
    owner_id: str,
) -> tuple[str, str, str, Path, str]:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    job = await material_job_repository.get_job(material.source_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    relative_path = material_job_service.resolve_concept_artifact_relative_path(
        record,
        concept_id,
        "resources_json",
    )
    if job.output_dir:
        await asyncio.to_thread(
            _storage.ensure_local_prefix,
            _storage.material_area,
            job.output_dir,
        )
    path = await asyncio.to_thread(
        _storage.ensure_local_copy,
        _storage.material_area,
        relative_path,
    )
    return subject.name, subject.grade_level, concept.name, path, job.output_dir or ""


async def get_admin_concept_resources(
    subject_id: str,
    concept_id: str,
    owner_id: str,
) -> ConceptResourcesResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    _, _, _, path, _ = await _resolve_concept_resources_path(subject_id, concept_id, owner_id)
    resources, _, _ = _load_resources(path, concept_id)
    approved = await study_material_repository.list_video_feedback(concept_id, status="approved")
    approved_id = approved[0].video_id if approved else None
    return ConceptResourcesResponse(
        concept_id=concept_id,
        concept_name=concept.name,
        subject_id=subject.id,
        subject_name=subject.name,
        resources=resources,
        approved_video_id=approved_id,
    )


async def refresh_admin_concept_video(
    subject_id: str,
    concept_id: str,
    payload: VideoFeedbackRequest,
    owner_id: str,
) -> ConceptResourcesResponse:
    subject_name, grade_level, concept_name, path, _ = await _resolve_concept_resources_path(
        subject_id, concept_id, owner_id
    )
    resources, existing_payload, payload_is_list = _load_resources(path, concept_id)

    reject_id = _extract_youtube_id(payload.url)
    if not reject_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid YouTube URL.")
    await study_material_repository.upsert_video_feedback(concept_id, reject_id, "rejected")
    rejected_rows = await study_material_repository.list_video_feedback(concept_id, status="rejected")
    rejected_ids = {row.video_id for row in rejected_rows}

    service = YouTubeVideoService()
    if not (service.settings.youtube_api_key or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YouTube API key is not configured.",
        )
    candidate = await service.find_best_video(
        subject_name=subject_name,
        grade_level=grade_level,
        concept_name=concept_name,
        exclude_video_ids=rejected_ids,
    )
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No alternative video found.")

    note = f"YouTube video (views: {candidate['views']:,}, likes: {candidate['likes']:,})"
    new_resource = ResourceItem(
        title=candidate["title"][:120],
        url=candidate["url"],
        note=note[:240],
    )

    replaced = False
    updated_resources: list[ResourceItem] = []
    for item in resources:
        if not replaced and _is_youtube_url(item.url):
            updated_resources.append(new_resource)
            replaced = True
        else:
            updated_resources.append(item)
    if not replaced:
        updated_resources.insert(0, new_resource)

    _write_resources(
        path,
        concept_id=concept_id,
        concept_name=concept_name,
        resources=updated_resources,
        existing_payload=existing_payload,
        payload_is_list=payload_is_list,
    )
    concept_dir = path.parent
    output_dir = concept_dir.parent.parent
    subject_resources_path = output_dir / "resources.json"
    _, subject_payload, _ = _load_resources(subject_resources_path, concept_id)
    if subject_resources_path.exists() or subject_payload:
        _write_resources(
            subject_resources_path,
            concept_id=concept_id,
            concept_name=concept_name,
            resources=updated_resources,
            existing_payload=subject_payload,
            payload_is_list=True,
        )
    concept_zip_path = _refresh_zip_bundle(concept_dir)
    output_zip_path = _refresh_zip_bundle(output_dir)
    await asyncio.to_thread(_storage.sync_local_file, _storage.material_area, path)
    if subject_resources_path.exists():
        await asyncio.to_thread(
            _storage.sync_local_file,
            _storage.material_area,
            subject_resources_path,
        )
    if concept_zip_path.exists():
        await asyncio.to_thread(
            _storage.sync_local_file,
            _storage.material_area,
            concept_zip_path,
        )
    if output_zip_path.exists():
        await asyncio.to_thread(
            _storage.sync_local_file,
            _storage.material_area,
            output_zip_path,
        )
    approved_rows = await study_material_repository.list_video_feedback(concept_id, status="approved")
    approved_id = approved_rows[0].video_id if approved_rows else None
    return ConceptResourcesResponse(
        concept_id=concept_id,
        concept_name=concept_name,
        subject_id=subject_id,
        subject_name=subject_name,
        resources=updated_resources,
        approved_video_id=approved_id,
    )


async def approve_admin_concept_video(
    subject_id: str,
    concept_id: str,
    payload: VideoFeedbackRequest,
    owner_id: str,
) -> ConceptResourcesResponse:
    subject_name, _, concept_name, path, _ = await _resolve_concept_resources_path(
        subject_id, concept_id, owner_id
    )
    resources, _, _ = _load_resources(path, concept_id)
    approve_id = _extract_youtube_id(payload.url)
    if not approve_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid YouTube URL.")
    await study_material_repository.upsert_video_feedback(concept_id, approve_id, "approved")
    return ConceptResourcesResponse(
        concept_id=concept_id,
        concept_name=concept_name,
        subject_id=subject_id,
        subject_name=subject_name,
        resources=resources,
        approved_video_id=approve_id,
    )
