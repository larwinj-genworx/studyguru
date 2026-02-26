from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, status

from ..agents import build_agent_registry
from ..config import get_settings
from ..graph.workflow import MaterialWorkflow
from ..models import (
    AdminMaterialApproveRequest,
    AdminMaterialJobCreate,
    AdminMaterialRegenerateRequest,
    JobRecord,
    JobStatus,
    MaterialJobStatusResponse,
)
from ..renderers.docx_renderer import DocxRenderer
from ..renderers.json_renderer import JsonRenderer
from ..renderers.pdf_renderer import PdfRenderer
from ..renderers.pptx_renderer import PptxRenderer
from ..store import store

logger = logging.getLogger("uvicorn.error")


class MaterialJobService:
    _allowed_artifacts = {
        "pptx",
        "docx",
        "pdf",
        "quiz_json",
        "flashcards_json",
        "resources_json",
        "zip",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self._workflow: MaterialWorkflow | None = None

    # ----- Admin generation lifecycle -----
    async def create_admin_job(self, payload: AdminMaterialJobCreate) -> MaterialJobStatusResponse:
        job = store.create_admin_job(payload)
        await self._run_job(job.job_id)
        return self._to_job_response(store.get_job(job.job_id))

    async def regenerate_job(
        self,
        source_job_id: str,
        payload: AdminMaterialRegenerateRequest,
    ) -> MaterialJobStatusResponse:
        source_job = store.get_job(source_job_id)
        create_payload = AdminMaterialJobCreate(
            subject_id=source_job.subject_id,
            concept_ids=source_job.concept_ids,
            learner_profile=payload.learner_profile or source_job.learner_profile,
        )
        revision_note = payload.revision_note or source_job.reviewer_note
        new_job = store.create_admin_job(create_payload, revision_note=revision_note)
        await self._run_job(new_job.job_id)
        return self._to_job_response(store.get_job(new_job.job_id))

    def approve_job(
        self,
        job_id: str,
        payload: AdminMaterialApproveRequest,
    ) -> MaterialJobStatusResponse:
        job = store.approve_job(job_id, payload)
        return self._to_job_response(job)

    def get_job_status(self, job_id: str) -> MaterialJobStatusResponse:
        return self._to_job_response(store.get_job(job_id))

    # ----- Artifact access -----
    def get_job_artifact_path(self, job_id: str, artifact_name: str) -> Path:
        job = store.get_job(job_id)
        self._assert_completed(job)
        self._validate_artifact_name(artifact_name)
        path = getattr(job.artifact_index, artifact_name, None)
        if not path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
        return self._validate_path(path)

    def get_job_concept_artifact_path(self, job_id: str, concept_id: str, artifact_name: str) -> Path:
        job = store.get_job(job_id)
        self._assert_completed(job)
        self._validate_artifact_name(artifact_name)
        concept_artifact = job.concept_artifacts.get(concept_id)
        if not concept_artifact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No generated artifact found for concept '{concept_id}'.",
            )
        path = getattr(concept_artifact, artifact_name, None)
        if not path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
        return self._validate_path(path)

    def get_published_concept_artifact_path(
        self,
        subject_id: str,
        concept_id: str,
        artifact_name: str,
    ) -> Path:
        self._validate_artifact_name(artifact_name)
        material = store.get_published_concept_material(subject_id, concept_id)
        path = getattr(material.artifact_index, artifact_name, None)
        if not path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published artifact not found.")
        return self._validate_path(path)

    # ----- Execution -----
    async def _run_job(self, job_id: str) -> None:
        try:
            workflow = self._ensure_workflow()
            await workflow.run(job_id)
        except Exception as exc:
            logger.exception("[MaterialJob:%s] Workflow execution failed.", job_id)
            job = store.get_job(job_id)
            job.status = JobStatus.failed
            job.errors.append(str(exc))
            job.progress = min(job.progress, 99)
            store.update_job(job)

    def _ensure_workflow(self) -> MaterialWorkflow:
        if self._workflow is not None:
            return self._workflow
        self._workflow = MaterialWorkflow(
            store=store,
            settings=self.settings,
            agents=build_agent_registry(self.settings),
            pptx_renderer=PptxRenderer(),
            docx_renderer=DocxRenderer(),
            pdf_renderer=PdfRenderer(),
            json_renderer=JsonRenderer(),
        )
        return self._workflow

    # ----- Helpers -----
    @classmethod
    def _validate_artifact_name(cls, artifact_name: str) -> None:
        if artifact_name not in cls._allowed_artifacts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported artifact name: {artifact_name}",
            )

    @staticmethod
    def _assert_completed(job: JobRecord) -> None:
        if job.status != JobStatus.completed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Artifacts are available only after job completion.",
            )

    @staticmethod
    def _validate_path(path_value: str) -> Path:
        path = Path(path_value).resolve()
        if not path.exists() or not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artifact file does not exist.",
            )
        return path

    @staticmethod
    def _to_job_response(job: JobRecord) -> MaterialJobStatusResponse:
        return MaterialJobStatusResponse(
            job_id=job.job_id,
            subject_id=job.subject_id,
            concept_ids=job.concept_ids,
            status=job.status,
            review_status=job.review_status,
            progress=job.progress,
            concept_statuses=job.concept_statuses,
            artifact_index=job.artifact_index,
            concept_artifacts=job.concept_artifacts,
            errors=job.errors,
            reviewer_note=job.reviewer_note,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


material_job_service = MaterialJobService()
