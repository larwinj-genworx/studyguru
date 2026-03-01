from __future__ import annotations

from sqlalchemy import select

from datetime import datetime, timezone

from src.core.services.auth_service import hash_password, verify_password
from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import User


async def get_user_by_id(user_id: str) -> User | None:
    async with AsyncSessionFactory() as session:
        return await session.get(User, user_id)


async def get_user_by_email(email: str) -> User | None:
    normalized = email.strip().lower()
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.email == normalized))
        return result.scalar_one_or_none()


async def create_user(email: str, password: str, role: str) -> User:
    normalized = email.strip().lower()
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user = User(
                email=normalized,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
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
