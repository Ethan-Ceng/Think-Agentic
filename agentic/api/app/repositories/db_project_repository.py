#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Database-backed Project repository."""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.project import (
    Project,
    ProjectNameConflictError,
    ProjectNotFoundError,
)
from app.models import ProjectModel
from app.repositories.project_repository import ProjectRepository


class DBProjectRepository(ProjectRepository):
    """PostgreSQL persistence with explicit user scoping on every lookup."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def list_by_user(self, user_id: str) -> list[Project]:
        statement = (
            select(ProjectModel)
            .where(ProjectModel.user_id == user_id)
            .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
        )
        records = (await self.db_session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def get_by_id_for_user(
        self,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        statement = select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        ).with_for_update(read=True)
        record = (await self.db_session.execute(statement)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def create(self, project: Project) -> Project:
        try:
            async with self.db_session.begin_nested():
                self.db_session.add(ProjectModel.from_domain(project))
                await self.db_session.flush()
        except IntegrityError as error:
            raise ProjectNameConflictError("项目名称已存在") from error
        return project

    async def rename(
        self,
        project_id: str,
        user_id: str,
        name: str,
    ) -> Project:
        statement = (
            select(ProjectModel)
            .where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
            )
            .with_for_update()
        )
        record = (await self.db_session.execute(statement)).scalar_one_or_none()
        if record is None:
            raise ProjectNotFoundError("项目不存在或无权访问")

        try:
            async with self.db_session.begin_nested():
                record.name = name
                record.updated_at = datetime.now()
                await self.db_session.flush()
        except IntegrityError as error:
            raise ProjectNameConflictError("项目名称已存在") from error
        return record.to_domain()

    async def delete(self, project_id: str, user_id: str) -> None:
        statement = delete(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.user_id == user_id,
        )
        result = await self.db_session.execute(statement)
        if not result.rowcount:
            raise ProjectNotFoundError("项目不存在或无权访问")
