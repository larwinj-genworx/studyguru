from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi import HTTPException
from fastapi.responses import FileResponse

from .auth import require_role
from .models import (
    AdminMaterialApproveRequest,
    AdminMaterialJobCreate,
    AdminMaterialRegenerateRequest,
    ConceptBulkCreate,
    ConceptMaterialResponse,
    ConceptResponse,
    MaterialJobStatusResponse,
    StudentConceptSelection,
    SubjectCreate,
    SubjectResponse,
)
from .operations.material_job_operations import (
    approve_job,
    create_admin_job,
    get_job_artifact_path,
    get_job_concept_artifact_path,
    get_job_status,
    get_published_concept_artifact_path,
    get_published_subject_artifact_path,
    regenerate_job,
)
from .store import store

router = APIRouter(tags=["study-material"])


# ----- Admin APIs -----
@router.post(
    "/admin/subjects",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_subject(payload: SubjectCreate) -> SubjectResponse:
    return store.create_subject(payload)


@router.post(
    "/admin/subjects/{subject_id}/concepts/bulk",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def add_concepts(subject_id: str, payload: ConceptBulkCreate) -> SubjectResponse:
    return store.add_concepts_bulk(subject_id, payload)


@router.get(
    "/admin/subjects/{subject_id}",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_subject(subject_id: str) -> SubjectResponse:
    return store.get_subject(subject_id)


@router.get(
    "/admin/subjects/{subject_id}/materials",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_admin_subject_materials(subject_id: str) -> list[ConceptMaterialResponse]:
    return store.list_subject_materials(subject_id, published_only=False)


@router.post(
    "/admin/material-jobs",
    response_model=MaterialJobStatusResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def create_admin_material_job(payload: AdminMaterialJobCreate) -> MaterialJobStatusResponse:
    return await create_admin_job(payload)


@router.get(
    "/admin/material-jobs/{job_id}",
    response_model=MaterialJobStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_material_job_status(job_id: str) -> MaterialJobStatusResponse:
    return get_job_status(job_id)


@router.post(
    "/admin/material-jobs/{job_id}/regenerate",
    response_model=MaterialJobStatusResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def regenerate_material_job(
    job_id: str,
    payload: AdminMaterialRegenerateRequest,
) -> MaterialJobStatusResponse:
    return await regenerate_job(job_id, payload)


@router.post(
    "/admin/material-jobs/{job_id}/approve",
    response_model=MaterialJobStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def approve_material_job(
    job_id: str,
    payload: AdminMaterialApproveRequest,
) -> MaterialJobStatusResponse:
    return approve_job(job_id, payload)


@router.get(
    "/admin/material-jobs/{job_id}/download.zip",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_job_zip(job_id: str) -> FileResponse:
    zip_path = get_job_artifact_path(job_id=job_id, artifact_name="zip")
    return FileResponse(path=str(zip_path), filename=zip_path.name, media_type="application/zip")


@router.get(
    "/admin/material-jobs/{job_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_job_artifact(job_id: str, artifact_name: str) -> FileResponse:
    artifact_path = get_job_artifact_path(job_id=job_id, artifact_name=artifact_name)
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.get(
    "/admin/material-jobs/{job_id}/concepts/{concept_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_concept_artifact(job_id: str, concept_id: str, artifact_name: str) -> FileResponse:
    artifact_path = get_job_concept_artifact_path(
        job_id=job_id,
        concept_id=concept_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.post(
    "/admin/subjects/{subject_id}/publish",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def publish_subject(subject_id: str) -> SubjectResponse:
    return store.publish_subject(subject_id)


# ----- Student APIs -----
@router.get(
    "/student/subjects",
    response_model=list[SubjectResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subjects() -> list[SubjectResponse]:
    return store.list_published_subjects()


@router.get(
    "/student/subjects/{subject_id}/concepts",
    response_model=list[ConceptResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_concepts(subject_id: str) -> list[ConceptResponse]:
    return store.list_subject_concepts(subject_id=subject_id, published_only=True)


@router.get(
    "/student/subjects/{subject_id}/materials",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_materials(subject_id: str) -> list[ConceptMaterialResponse]:
    return store.list_subject_materials(subject_id, published_only=True)


@router.post(
    "/student/subjects/{subject_id}/materials/query",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def query_selected_concept_materials(
    subject_id: str,
    payload: StudentConceptSelection,
) -> list[ConceptMaterialResponse]:
    published_materials = {
        item.concept_id: item
        for item in store.list_subject_materials(subject_id, published_only=True)
    }
    missing = [concept_id for concept_id in payload.concept_ids if concept_id not in published_materials]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Published material not available for concept IDs: {missing}",
        )
    return [published_materials[concept_id] for concept_id in payload.concept_ids]


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_concept_artifact(subject_id: str, concept_id: str, artifact_name: str) -> FileResponse:
    artifact_path = get_published_concept_artifact_path(
        subject_id=subject_id,
        concept_id=concept_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.get(
    "/student/subjects/{subject_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_subject_artifact(subject_id: str, artifact_name: str) -> FileResponse:
    artifact_path = get_published_subject_artifact_path(
        subject_id=subject_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)
