from __future__ import annotations

from sqlalchemy import select

from datetime import datetime, timezone
from uuid import uuid4

from src.core.services.auth_service import hash_password, verify_password
from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import Organization, User


async def get_user_by_id(user_id: str) -> User | None:
    async with AsyncSessionFactory() as session:
        return await session.get(User, user_id)


async def get_organization_by_id(organization_id: str) -> Organization | None:
    async with AsyncSessionFactory() as session:
        return await session.get(Organization, organization_id)


async def get_user_by_email(email: str) -> User | None:
    normalized = email.strip().lower()
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.email == normalized))
        return result.scalar_one_or_none()


async def list_users_by_ids(user_ids: list[str]) -> list[User]:
    if not user_ids:
        return []
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.id.in_(user_ids)))
        return result.scalars().all()


async def list_users_for_organization(
    organization_id: str,
    *,
    role: str | None = None,
) -> list[User]:
    async with AsyncSessionFactory() as session:
        stmt = select(User).where(User.organization_id == organization_id)
        if role:
            stmt = stmt.where(User.role == role)
        stmt = stmt.order_by(User.created_at.desc(), User.email.asc())
        result = await session.execute(stmt)
        return result.scalars().all()


async def create_organization(name: str) -> Organization:
    normalized_name = name.strip()
    async with AsyncSessionFactory() as session:
        async with session.begin():
            organization = Organization(
                id=uuid4().hex,
                name=normalized_name,
                is_active=True,
            )
            session.add(organization)
        return organization


async def create_user(
    email: str,
    password: str,
    role: str,
    *,
    organization_id: str,
    is_active: bool = True,
) -> User:
    normalized = email.strip().lower()
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user = User(
                email=normalized,
                password_hash=hash_password(password),
                role=role,
                organization_id=organization_id,
                is_active=is_active,
            )
            session.add(user)
        return user


async def verify_user_credentials(email: str, password: str) -> User | None:
    user = await get_user_by_email(email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_user = await session.get(User, user.id)
            if db_user:
                now = datetime.now(timezone.utc)
                db_user.last_login_at = now
                db_user.updated_at = now
        return user


async def update_user_password(user_id: str, password: str) -> User | None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return None
            user.password_hash = hash_password(password)
            user.updated_at = datetime.now(timezone.utc)
        return user


async def update_user_active_state(user_id: str, is_active: bool) -> User | None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user = await session.get(User, user_id)
            if not user:
                return None
            user.is_active = is_active
            user.updated_at = datetime.now(timezone.utc)
        return user
