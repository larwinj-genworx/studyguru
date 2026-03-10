from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from src.api.rest.dependencies import get_current_user, require_role
from src.core.services import concept_image_app_service, enrollment_app_service, learning_bot_app_service, material_job_app_service, study_material_app_service
from src.core.services import resource_review_app_service
from src.schemas.concept_images import ConceptImageCollectionResponse, ConceptImageGenerationRequest
from src.schemas.learning_bot import (
    LearningBotMessageCreate,
    LearningBotSessionDetailResponse,
    LearningBotTurnResponse,
)
from src.schemas.study_material import (
    AdminMaterialApproveRequest,
    AdminMaterialJobCreate,
    AdminEnrolledStudentResponse,
    AdminStudentActivityResponse,
    AdminMaterialPublishRequest,
    AdminMaterialRegenerateRequest,
    ConceptBulkCreate,
    ConceptBookmarkResponse,
    ConceptMaterialResponse,
    ConceptResponse,
    ConceptResourcesResponse,
    LearningContentResponse,
    LearningContentUpdate,
    MaterialJobStatusResponse,
    StudentConceptSelection,
    SubjectCreate,
    SubjectEnrollmentResponse,
    SubjectResponse,
    VideoFeedbackRequest,
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


@router.delete(
    "/admin/subjects/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_subject(
    subject_id: str,
    force: bool = False,
    current_user: dict = Depends(get_current_user),
) -> None:
    await study_material_app_service.delete_subject(
        subject_id,
        owner_id=current_user["id"],
        force=force,
    )


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


@router.get(
    "/admin/subjects/{subject_id}/enrollments",
    response_model=list[AdminEnrolledStudentResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_admin_subject_enrollments(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[AdminEnrolledStudentResponse]:
    return await enrollment_app_service.list_admin_subject_enrollments(
        subject_id=subject_id,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects/{subject_id}/students/{student_id}/activity",
    response_model=AdminStudentActivityResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_student_activity(
    subject_id: str,
    student_id: str,
    current_user: dict = Depends(get_current_user),
) -> AdminStudentActivityResponse:
    return await enrollment_app_service.get_admin_student_activity(
        subject_id=subject_id,
        student_id=student_id,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects/{subject_id}/approved-materials.zip",
    dependencies=[Depends(require_role("admin"))],
)
async def download_approved_materials_bundle(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    bundle_path = await study_material_app_service.get_approved_subject_bundle_path(
        subject_id=subject_id,
        owner_id=current_user["id"],
    )
    return FileResponse(
        path=str(bundle_path),
        filename=bundle_path.name,
        media_type="application/zip",
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


@router.delete(
    "/admin/material-jobs/{job_id}/concepts/{concept_id}",
    response_model=MaterialJobStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def discard_material_job_concept(
    job_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> MaterialJobStatusResponse:
    return await material_job_app_service.discard_job_concept(
        job_id=job_id,
        concept_id=concept_id,
        owner_id=current_user["id"],
    )


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


@router.post(
    "/admin/subjects/{subject_id}/publish/concepts",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def publish_selected_concepts(
    subject_id: str,
    payload: AdminMaterialPublishRequest,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.publish_selected_concepts(
        subject_id,
        concept_ids=payload.concept_ids,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/subjects/{subject_id}/unpublish",
    response_model=SubjectResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def unpublish_subject(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> SubjectResponse:
    return await study_material_app_service.unpublish_subject(subject_id, owner_id=current_user["id"])


@router.get(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/learning",
    response_model=LearningContentResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_learning_content(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> LearningContentResponse:
    return await study_material_app_service.get_admin_concept_learning_content(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=current_user["id"],
    )


@router.patch(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/learning",
    response_model=LearningContentResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_admin_learning_content(
    subject_id: str,
    concept_id: str,
    payload: LearningContentUpdate,
    current_user: dict = Depends(get_current_user),
) -> LearningContentResponse:
    return await study_material_app_service.update_admin_concept_learning_content(
        subject_id=subject_id,
        concept_id=concept_id,
        payload=payload,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/resources",
    response_model=ConceptResourcesResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_concept_resources(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConceptResourcesResponse:
    return await resource_review_app_service.get_admin_concept_resources(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/resources/videos/refresh",
    response_model=ConceptResourcesResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def refresh_admin_concept_video(
    subject_id: str,
    concept_id: str,
    payload: VideoFeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> ConceptResourcesResponse:
    return await resource_review_app_service.refresh_admin_concept_video(
        subject_id=subject_id,
        concept_id=concept_id,
        payload=payload,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/resources/videos/approve",
    response_model=ConceptResourcesResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def approve_admin_concept_video(
    subject_id: str,
    concept_id: str,
    payload: VideoFeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> ConceptResourcesResponse:
    return await resource_review_app_service.approve_admin_concept_video(
        subject_id=subject_id,
        concept_id=concept_id,
        payload=payload,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/images",
    response_model=ConceptImageCollectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_concept_images(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConceptImageCollectionResponse:
    return await concept_image_app_service.get_admin_concept_images(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/images/generate",
    response_model=ConceptImageCollectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def generate_admin_concept_images(
    subject_id: str,
    concept_id: str,
    payload: ConceptImageGenerationRequest,
    current_user: dict = Depends(get_current_user),
) -> ConceptImageCollectionResponse:
    return await concept_image_app_service.generate_admin_concept_images(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=current_user["id"],
        prompt=payload.prompt,
        refresh=payload.refresh,
    )


@router.post(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/images/{image_id}/approve",
    response_model=ConceptImageCollectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def approve_admin_concept_image(
    subject_id: str,
    concept_id: str,
    image_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConceptImageCollectionResponse:
    return await concept_image_app_service.approve_admin_concept_image(
        subject_id=subject_id,
        concept_id=concept_id,
        image_id=image_id,
        owner_id=current_user["id"],
    )


@router.post(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/images/{image_id}/reject",
    response_model=ConceptImageCollectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def reject_admin_concept_image(
    subject_id: str,
    concept_id: str,
    image_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConceptImageCollectionResponse:
    return await concept_image_app_service.reject_admin_concept_image(
        subject_id=subject_id,
        concept_id=concept_id,
        image_id=image_id,
        owner_id=current_user["id"],
    )


@router.get(
    "/admin/subjects/{subject_id}/concepts/{concept_id}/images/{image_id}/file",
    dependencies=[Depends(require_role("admin"))],
)
async def download_admin_concept_image_file(
    subject_id: str,
    concept_id: str,
    image_id: str,
    variant: str = Query(default="full"),
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    path = await concept_image_app_service.get_admin_concept_image_file_path(
        subject_id=subject_id,
        concept_id=concept_id,
        image_id=image_id,
        owner_id=current_user["id"],
        variant=variant,
    )
    return FileResponse(path=str(path), filename=path.name)


# ----- Student APIs -----
@router.get(
    "/student/subjects",
    response_model=list[SubjectResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subjects(
    current_user: dict = Depends(get_current_user),
) -> list[SubjectResponse]:
    return await enrollment_app_service.list_student_subjects(current_user["id"])


@router.post(
    "/student/subjects/{subject_id}/enroll",
    response_model=SubjectEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("student"))],
)
async def enroll_student_subject(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> SubjectEnrollmentResponse:
    return await enrollment_app_service.enroll_student(subject_id, current_user["id"])


@router.get(
    "/student/subjects/{subject_id}/concepts",
    response_model=list[ConceptResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_concepts(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[ConceptResponse]:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await study_material_app_service.list_subject_concepts(subject_id=subject_id, published_only=True)


@router.get(
    "/student/subjects/{subject_id}/materials",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_published_subject_materials(
    subject_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[ConceptMaterialResponse]:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await study_material_app_service.list_subject_materials(subject_id, published_only=True)


@router.post(
    "/student/subjects/{subject_id}/materials/query",
    response_model=list[ConceptMaterialResponse],
    dependencies=[Depends(require_role("student"))],
)
async def query_selected_concept_materials(
    subject_id: str,
    payload: StudentConceptSelection,
    current_user: dict = Depends(get_current_user),
) -> list[ConceptMaterialResponse]:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await study_material_app_service.query_selected_concept_materials(
        subject_id, payload.concept_ids
    )


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_concept_artifact(
    subject_id: str,
    concept_id: str,
    artifact_name: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    artifact_path = await material_job_app_service.get_published_concept_artifact_path(
        subject_id=subject_id,
        concept_id=concept_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/learning",
    response_model=LearningContentResponse,
    dependencies=[Depends(require_role("student"))],
)
async def get_student_learning_content(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> LearningContentResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await study_material_app_service.get_student_concept_learning_content(
        subject_id=subject_id,
        concept_id=concept_id,
    )


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/learning-bot/session",
    response_model=LearningBotSessionDetailResponse,
    dependencies=[Depends(require_role("student"))],
)
async def get_student_learning_bot_session(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> LearningBotSessionDetailResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await learning_bot_app_service.get_student_learning_bot_session(
        subject_id=subject_id,
        concept_id=concept_id,
        user_id=current_user["id"],
    )


@router.post(
    "/student/subjects/{subject_id}/concepts/{concept_id}/learning-bot/messages",
    response_model=LearningBotTurnResponse,
    dependencies=[Depends(require_role("student"))],
)
async def send_student_learning_bot_message(
    subject_id: str,
    concept_id: str,
    payload: LearningBotMessageCreate,
    current_user: dict = Depends(get_current_user),
) -> LearningBotTurnResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await learning_bot_app_service.send_student_learning_bot_message(
        subject_id=subject_id,
        concept_id=concept_id,
        user_id=current_user["id"],
        payload=payload,
    )


@router.post(
    "/student/subjects/{subject_id}/concepts/{concept_id}/learning-bot/session/reset",
    response_model=LearningBotSessionDetailResponse,
    dependencies=[Depends(require_role("student"))],
)
async def reset_student_learning_bot_session(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> LearningBotSessionDetailResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await learning_bot_app_service.reset_student_learning_bot_session(
        subject_id=subject_id,
        concept_id=concept_id,
        user_id=current_user["id"],
    )


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/images",
    response_model=ConceptImageCollectionResponse,
    dependencies=[Depends(require_role("student"))],
)
async def list_student_concept_images(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConceptImageCollectionResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    return await concept_image_app_service.list_student_concept_images(
        subject_id=subject_id,
        concept_id=concept_id,
    )


@router.get(
    "/student/subjects/{subject_id}/concepts/{concept_id}/images/{image_id}/file",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_concept_image_file(
    subject_id: str,
    concept_id: str,
    image_id: str,
    variant: str = Query(default="full"),
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    path = await concept_image_app_service.get_student_concept_image_file_path(
        subject_id=subject_id,
        concept_id=concept_id,
        image_id=image_id,
        variant=variant,
    )
    return FileResponse(path=str(path), filename=path.name)


@router.get(
    "/student/bookmarks",
    response_model=list[ConceptBookmarkResponse],
    dependencies=[Depends(require_role("student"))],
)
async def list_student_bookmarks(
    subject_id: str | None = None,
    current_user: dict = Depends(get_current_user),
) -> list[ConceptBookmarkResponse]:
    return await study_material_app_service.list_student_bookmarks(
        user_id=current_user["id"],
        subject_id=subject_id,
    )


@router.post(
    "/student/subjects/{subject_id}/concepts/{concept_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("student"))],
)
async def add_student_bookmark(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    await study_material_app_service.add_student_bookmark(
        user_id=current_user["id"],
        subject_id=subject_id,
        concept_id=concept_id,
    )


@router.delete(
    "/student/subjects/{subject_id}/concepts/{concept_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("student"))],
)
async def remove_student_bookmark(
    subject_id: str,
    concept_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    await study_material_app_service.remove_student_bookmark(
        user_id=current_user["id"],
        concept_id=concept_id,
    )


@router.get(
    "/student/subjects/{subject_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_role("student"))],
)
async def download_student_subject_artifact(
    subject_id: str,
    artifact_name: str,
    current_user: dict = Depends(get_current_user),
) -> FileResponse:
    await enrollment_app_service.ensure_student_enrollment(subject_id, current_user["id"])
    artifact_path = await material_job_app_service.get_published_subject_artifact_path(
        subject_id=subject_id,
        artifact_name=artifact_name,
    )
    return FileResponse(path=str(artifact_path), filename=artifact_path.name)
