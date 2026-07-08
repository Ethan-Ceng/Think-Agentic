#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Database-backed config repository."""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.config import Config
from app.models import ConfigModel
from app.repositories.config_repository import ConfigRepository


class DBConfigRepository(ConfigRepository):
    """PostgreSQL config repository."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def save(self, config: Config) -> None:
        stmt = select(ConfigModel).where(ConfigModel.id == config.id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            by_type = await self.db_session.execute(
                select(ConfigModel).where(
                    ConfigModel.user_id == config.user_id,
                    ConfigModel.config_type == config.config_type,
                )
            )
            record = by_type.scalar_one_or_none()

        if not record:
            self.db_session.add(ConfigModel.from_domain(config))
            return

        record.update_from_domain(config)

    async def get_by_user_and_type(self, user_id: str, config_type: str) -> Optional[Config]:
        stmt = select(ConfigModel).where(
            ConfigModel.user_id == user_id,
            ConfigModel.config_type == config_type,
        )
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def get_all_by_user(self, user_id: str) -> List[Config]:
        stmt = select(ConfigModel).where(ConfigModel.user_id == user_id)
        result = await self.db_session.execute(stmt)
        records = result.scalars().all()
        return [record.to_domain() for record in records]
