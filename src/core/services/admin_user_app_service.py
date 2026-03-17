from __future__ import annotations

from fastapi import HTTPException, status

from src.core.services import enrollment_app_service
from src.data.models.postgres.models import Organization, User
from src.data.repositories import auth_repository, study_material_repository
from src.schemas.auth import (
    AdminManagedStudentCreateRequest,
    AdminManagedStudentResponse,
    AdminManagedStudentUpdateRequest,
    ManagedStudentSubjectResponse,
    PlatformAdminProvisionRequest,
)


async def provision_organization_admin(
    payload: PlatformAdminProvisionRequest,
) -> tuple[Organization, User]:
    existing = await auth_repository.get_user_by_email(payload.admin_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    organization = await auth_repository.create_organization(payload.organization_name)
    user = await auth_repository.create_user(
        payload.admin_email,
        payload.password,
        "admin",
        organization_id=organization.id,
    )
    return organization, user


async def list_managed_students(organization_id: str) -> list[AdminManagedStudentResponse]:
    students = await auth_repository.list_users_for_organization(organization_id, role="student")
    return await _build_student_responses(students, organization_id)


async def create_managed_student(
    payload: AdminManagedStudentCreateRequest,
    organization_id: str,
) -> AdminManagedStudentResponse:
    existing = await auth_repository.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = await auth_repository.create_user(
        payload.email,
        payload.password,
        "student",
        organization_id=organization_id,
    )
    await enrollment_app_service.sync_organization_subject_access(
        organization_id,
        student_ids=[user.id],
    )

    return await get_managed_student(user.id, organization_id)


async def update_managed_student(
    student_id: str,
    payload: AdminManagedStudentUpdateRequest,
    organization_id: str,
) -> AdminManagedStudentResponse:
    student = await _get_student_or_404(student_id, organization_id)

    if payload.password is not None:
        await auth_repository.update_user_password(student.id, payload.password)
    if payload.is_active is not None:
        await auth_repository.update_user_active_state(student.id, payload.is_active)

    return await get_managed_student(student.id, organization_id)


async def get_managed_student(
    student_id: str,
    organization_id: str,
) -> AdminManagedStudentResponse:
    student = await _get_student_or_404(student_id, organization_id)
    responses = await _build_student_responses([student], organization_id)
    return responses[0]


async def _get_student_or_404(student_id: str, organization_id: str) -> User:
    student = await auth_repository.get_user_by_id(student_id)
    if not student or student.role.lower() != "student" or student.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return student


async def _build_student_responses(
    students: list[User],
    organization_id: str,
) -> list[AdminManagedStudentResponse]:
    if not students:
        return []

    subjects = sorted(
        await study_material_repository.list_subjects_for_organization(organization_id),
        key=lambda item: (item.name.lower(), item.created_at),
    )
    visible_subjects = [
        ManagedStudentSubjectResponse(
            subject_id=subject.id,
            name=subject.name,
            published=subject.published,
        )
        for subject in subjects
    ]

    responses: list[AdminManagedStudentResponse] = []
    for student in students:
        responses.append(
            AdminManagedStudentResponse(
                user_id=student.id,
                email=student.email,
                is_active=student.is_active,
                created_at=student.created_at,
                updated_at=student.updated_at,
                last_login_at=student.last_login_at,
                assigned_subjects=list(visible_subjects),
            )
        )
    return responses
