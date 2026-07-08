#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Database-backed user repository."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.user import User
from app.models import UserModel
from app.repositories.user_repository import UserRepository


class DBUserRepository(UserRepository):
    """PostgreSQL user repository."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def save(self, user: User) -> None:
        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            self.db_session.add(UserModel.from_domain(user))
            return

        record.update_from_domain(user)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record is not None else None
