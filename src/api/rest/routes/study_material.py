from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from src.api.rest.dependencies import get_current_user, require_role
from src.core.services import material_job_app_service, study_material_app_service
from src.schemas.study_material import (
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

router = APIRouter(tags=["study-material"])


# ----- Admin APIs -----
@router.post(
    "/admin/subjects",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_subject(
    payload: SubjectCreate,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.create_subject(payload, owner_id=current_user["id"])


@router.post(
    "/admin/subjects/{subject_id}/concepts/bulk",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def add_concepts(
    subject_id: str,
    payload: ConceptBulkCreate,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.add_concepts_bulk(
        subject_id,
        payload,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects",
    response_model=list[SubjectResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_admin_subjects(current_user: dict = Depends(get_current_user)) -> list[SubjectResponse]:
    return await study_material_app_service.list_admin_subjects(owner_id=current_user["id"])


@router.get(
    "/admin/subjects/{subject_id}",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_subject(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.get_subject(subject_id, owner_id=current_user["id"])


@router.get(
    "/admin/subjects/{subject_id}/materials",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_admin_subject_materials(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[ConceptMaterialResponse]:
    return await study_material_app_service.list_subject_materials(
        subject_id,
        published_only=False,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/material-jobs",
    response_model=MaterialJobStatusResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def create_admin_material_job(
    payload: AdminMaterialJobCreate,
    current_user: dict = Depends(get_current_user),
) -> MaterialJobStatusResponse:
    return await material_job_app_service.create_admin_job(payload, owner_id=current_user["id"])


@router.get(
    "/admin/material-jobs",
    response_model=list[MaterialJobStatusResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_admin_material_jobs(
    subject_id: str | None = None,
    current_user: dict = Depends(get_current_user),
) -> list[MaterialJobStatusResponse]:
    return await material_job_app_service.list_admin_jobs(subject_id, owner_id=current_user["id"])


@router.get(
    "/admin/material-jobs/{job_id}",
    response_model=MaterialJobStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_material_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> MaterialJobStatusResponse:
    return await material_job_app_service.get_job_status(job_id, owner_id=current_user["id"])


@router.post(
    "/admin/material-jobs/{job_id}/regenerate",
    response_model=MaterialJobStatusResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("admin"))],
)
async def regenerate_material_job(
    job_id: str,
    payload: AdminMaterialRegenerateRequest,
    current_user: dict = Depends(get_current_user),
) -> MaterialJobStatusResponse:
    return await material_job_app_service.regenerate_job(job_id, payload, owner_id=current_user["id"])


@router.post(
    "/admin/material-jobs/{job_id}/approve",
    response_model=MaterialJobStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def approve_material_job(
    job_id: str,
    payload: AdminMaterialApproveRequest,
    current_user: dict = Depends(get_current_user),
) -> MaterialJobStatusResponse:
    return await material_job_app_service.approve_job(job_id, payload, owner_id=current_user["id"])


@router.get(
    "/admin/material-jobs/{job_id}/download.zip",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_job_zip(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    zip_path = await material_job_app_service.get_job_artifact_path(
        job_id=job_id,
        artifact_name="zip",
        owner_id=current_user["id"],
    )
    return FileResponse(path=str(zip_path), filename=zip_path.name, media_type="application/zip")


@router.get(
    "/admin/material-jobs/{job_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_job_artifact(
    job_id: str,
    artifact_name: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    artifact_path = await material_job_app_service.get_job_artifact_path(
        job_id=job_id,
        artifact_name=artifact_name,
        owner_id=current_user["id"],
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.get(
    "/admin/material-jobs/{job_id}/concepts/{concept_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_concept_artifact(
    job_id: str,
    concept_id: str,
    artifact_name: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    artifact_path = await material_job_app_service.get_job_concept_artifact_path(
        job_id=job_id,
        concept_id=concept_id,
        artifact_name=artifact_name,
        owner_id=current_user["id"],
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.post(
    "/admin/subjects/{subject_id}/publish",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def publish_subject(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.publish_subject(subject_id, owner_id=current_user["id"])


# ----- Student APIs -----
@router.get(
    "/student/subjects",
    response_model=list[SubjectResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subjects() -> list[SubjectResponse]:
    return await study_material_app_service.list_published_subjects()


@router.get(
    "/student/subjects/{subject_id}/concepts",
    response_model=list[ConceptResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_concepts(subject_id: str) -> list[ConceptResponse]:
    return await study_material_app_service.list_subject_concepts(subject_id=subject_id, published_only=True)


@router.get(
    "/student/subjects/{subject_id}/materials",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_materials(subject_id: str) -> list[ConceptMaterialResponse]:
    return await study_material_app_service.list_subject_materials(subject_id, published_only=True)


@router.post(
    "/student/subjects/{subject_id}/materials/query",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def query_selected_concept_materials(
    subject_id: str,
    payload: StudentConceptSelection,
) -> list[ConceptMaterialResponse]:
    return await study_material_app_service.query_selected_concept_materials(
        subject_id, payload.concept_ids
    )


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_concept_artifact(subject_id: str, concept_id: str, artifact_name: str) -> FileResponse:
    artifact_path = await material_job_app_service.get_published_concept_artifact_path(
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
    artifact_path = await material_job_app_service.get_published_subject_artifact_path(
        subject_id=subject_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)
