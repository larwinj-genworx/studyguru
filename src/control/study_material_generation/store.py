from __future__ import annotations

from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, status

from .models import (
    AdminMaterialApproveRequest,
    AdminMaterialJobCreate,
    ConceptBulkCreate,
    ConceptMaterialRecord,
    ConceptMaterialResponse,
    ConceptResponse,
    JobRecord,
    JobStatus,
    MaterialLifecycleStatus,
    ReviewStatus,
    SubjectCreate,
    SubjectRecord,
    SubjectResponse,
    utc_now,
)


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subjects: dict[str, SubjectRecord] = {}
        self._jobs: dict[str, JobRecord] = {}

    # ----- Subject / Concept -----
    def create_subject(self, payload: SubjectCreate) -> SubjectResponse:
        with self._lock:
            subject = SubjectRecord(
                subject_id=uuid4().hex,
                name=payload.name.strip(),
                grade_level=payload.grade_level.strip(),
                description=payload.description,
            )
            self._subjects[subject.subject_id] = subject
            return self._to_subject_response(subject)

    def add_concepts_bulk(self, subject_id: str, payload: ConceptBulkCreate) -> SubjectResponse:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            for concept in payload.concepts:
                concept_id = uuid4().hex
                subject.concept_meta[concept_id] = ConceptResponse(
                    concept_id=concept_id,
                    name=concept.name.strip(),
                    description=concept.description,
                    created_at=utc_now(),
                )
            subject.updated_at = utc_now()
            return self._to_subject_response(subject)

    def publish_subject(self, subject_id: str) -> SubjectResponse:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            if not subject.concept_meta:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot publish a subject without concepts.",
                )

            missing_approved: list[str] = []
            for concept_id, concept in subject.concept_meta.items():
                material = subject.materials.get(concept_id)
                if not material or material.lifecycle_status not in (
                    MaterialLifecycleStatus.approved,
                    MaterialLifecycleStatus.published,
                ):
                    missing_approved.append(concept.name)

            if missing_approved:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Cannot publish until all concepts have approved materials. Missing approvals for: "
                        f"{missing_approved}"
                    ),
                )

            publish_time = utc_now()
            subject.published = True
            for material in subject.materials.values():
                material.lifecycle_status = MaterialLifecycleStatus.published
                material.published_at = publish_time
                concept_meta = subject.concept_meta[material.concept_id]
                concept_meta.material_status = MaterialLifecycleStatus.published
                concept_meta.material_version = material.version
            subject.updated_at = publish_time
            return self._to_subject_response(subject)

    def get_subject(self, subject_id: str) -> SubjectResponse:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            return self._to_subject_response(subject)

    def get_subject_record(self, subject_id: str) -> SubjectRecord:
        with self._lock:
            return self._get_subject_or_404(subject_id).model_copy(deep=True)

    def list_subject_materials(self, subject_id: str, published_only: bool = False) -> list[ConceptMaterialResponse]:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            if published_only and not subject.published:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subject is not published.",
                )
            materials: list[ConceptMaterialResponse] = []
            for concept_id, concept in subject.concept_meta.items():
                material = subject.materials.get(concept_id)
                if not material:
                    continue
                if published_only and material.lifecycle_status != MaterialLifecycleStatus.published:
                    continue
                materials.append(self._to_material_response(material))
            return materials

    def list_published_subjects(self) -> list[SubjectResponse]:
        with self._lock:
            return [
                self._to_subject_response(subject)
                for subject in self._subjects.values()
                if subject.published
            ]

    def list_subject_concepts(self, subject_id: str, published_only: bool = False) -> list[ConceptResponse]:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            if published_only and not subject.published:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subject not available for students.",
                )
            concepts = list(subject.concept_meta.values())
            if published_only:
                concepts = [
                    concept
                    for concept in concepts
                    if concept.material_status == MaterialLifecycleStatus.published
                ]
            return [concept.model_copy(deep=True) for concept in concepts]

    # ----- Admin Jobs -----
    def create_admin_job(self, payload: AdminMaterialJobCreate, revision_note: str | None = None) -> JobRecord:
        with self._lock:
            subject = self._get_subject_or_404(payload.subject_id)
            if not subject.concept_meta:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No concepts are available under this subject.",
                )

            concept_ids = list(dict.fromkeys(payload.concept_ids))
            missing = [concept_id for concept_id in concept_ids if concept_id not in subject.concept_meta]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown concept IDs: {missing}",
                )

            job = JobRecord(
                subject_id=payload.subject_id,
                concept_ids=concept_ids,
                learner_profile=payload.learner_profile,
                revision_note=revision_note,
                concept_statuses={concept_id: "queued" for concept_id in concept_ids},
            )
            self._jobs[job.job_id] = job
            return job.model_copy(deep=True)

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
            return job.model_copy(deep=True)

    def update_job(self, job: JobRecord) -> None:
        with self._lock:
            if job.job_id not in self._jobs:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
            job.touch()
            self._jobs[job.job_id] = job

    def approve_job(self, job_id: str, payload: AdminMaterialApproveRequest) -> JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
            if job.status != JobStatus.completed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Job is not completed yet.",
                )
            if job.review_status == ReviewStatus.approved:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This job is already approved.",
                )

            subject = self._get_subject_or_404(job.subject_id)
            target_ids = payload.concept_ids or job.concept_ids
            unknown = [concept_id for concept_id in target_ids if concept_id not in job.concept_artifacts]
            if unknown:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Concept artifacts missing in job output: {unknown}",
                )

            approve_time = utc_now()
            for concept_id in target_ids:
                concept = subject.concept_meta[concept_id]
                current_material = subject.materials.get(concept_id)
                next_version = (current_material.version + 1) if current_material else 1

                material = ConceptMaterialRecord(
                    concept_id=concept_id,
                    concept_name=concept.name,
                    lifecycle_status=MaterialLifecycleStatus.approved,
                    version=next_version,
                    source_job_id=job.job_id,
                    artifact_index=job.concept_artifacts[concept_id].model_copy(deep=True),
                    generated_at=approve_time,
                    approved_at=approve_time,
                )
                subject.materials[concept_id] = material
                concept.material_status = MaterialLifecycleStatus.approved
                concept.material_version = material.version

            job.review_status = ReviewStatus.approved
            job.reviewer_note = payload.approval_note
            job.reviewed_at = approve_time
            subject.updated_at = approve_time
            self._jobs[job.job_id] = job
            self._subjects[subject.subject_id] = subject
            return job.model_copy(deep=True)

    def get_published_concept_material(self, subject_id: str, concept_id: str) -> ConceptMaterialRecord:
        with self._lock:
            subject = self._get_subject_or_404(subject_id)
            if not subject.published:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subject is not published.",
                )
            material = subject.materials.get(concept_id)
            if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Published concept material not found.",
                )
            return material.model_copy(deep=True)

    # ----- Internal helpers -----
    def _get_subject_or_404(self, subject_id: str) -> SubjectRecord:
        subject = self._subjects.get(subject_id)
        if not subject:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
        return subject

    def _to_subject_response(self, subject: SubjectRecord) -> SubjectResponse:
        concepts = [concept.model_copy(deep=True) for concept in subject.concept_meta.values()]
        return SubjectResponse(
            subject_id=subject.subject_id,
            name=subject.name,
            grade_level=subject.grade_level,
            description=subject.description,
            published=subject.published,
            created_at=subject.created_at,
            updated_at=subject.updated_at,
            concepts=concepts,
        )

    @staticmethod
    def _to_material_response(material: ConceptMaterialRecord) -> ConceptMaterialResponse:
        return ConceptMaterialResponse(
            concept_id=material.concept_id,
            concept_name=material.concept_name,
            lifecycle_status=material.lifecycle_status,
            version=material.version,
            source_job_id=material.source_job_id,
            artifact_index=material.artifact_index,
            generated_at=material.generated_at,
            approved_at=material.approved_at,
            published_at=material.published_at,
        )


store = InMemoryStore()
