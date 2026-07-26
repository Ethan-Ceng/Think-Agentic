#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Application service for user-owned, single-level Projects."""
import logging
from collections.abc import Callable

from app.core.entities.project import (
    Project,
    ProjectNameConflictError,
    ProjectNotFoundError,
)
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


class ProjectService:
    """Manage navigation directories without touching Session content."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def list_projects(self, user_id: str) -> list[Project]:
        uow = self._uow_factory()
        async with uow:
            projects = await uow.project.list_by_user(user_id)
        self._log("list", user_id, result="success", count=len(projects))
        return projects

    async def create_project(self, user_id: str, name: str) -> Project:
        project = Project(user_id=user_id, name=name)
        try:
            uow = self._uow_factory()
            async with uow:
                created = await uow.project.create(project)
        except ProjectNameConflictError as error:
            self._log(
                "create",
                user_id,
                project_id=project.id,
                result="conflict",
            )
            raise ConflictError("已存在同名项目") from error
        self._log(
            "create",
            user_id,
            project_id=created.id,
            result="success",
        )
        return created

    async def rename_project(
        self,
        project_id: str,
        user_id: str,
        name: str,
    ) -> Project:
        try:
            uow = self._uow_factory()
            async with uow:
                renamed = await uow.project.rename(
                    project_id,
                    user_id,
                    name,
                )
        except ProjectNotFoundError as error:
            self._log(
                "rename",
                user_id,
                project_id=project_id,
                result="not_found",
            )
            raise NotFoundError("项目不存在或无权访问") from error
        except ProjectNameConflictError as error:
            self._log(
                "rename",
                user_id,
                project_id=project_id,
                result="conflict",
            )
            raise ConflictError("已存在同名项目") from error
        self._log(
            "rename",
            user_id,
            project_id=project_id,
            result="success",
        )
        return renamed

    async def delete_project(self, project_id: str, user_id: str) -> None:
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.project.delete(project_id, user_id)
        except ProjectNotFoundError as error:
            self._log(
                "delete",
                user_id,
                project_id=project_id,
                result="not_found",
            )
            raise NotFoundError("项目不存在或无权访问") from error
        self._log(
            "delete",
            user_id,
            project_id=project_id,
            result="success",
        )

    @staticmethod
    def _log(
        action: str,
        user_id: str,
        *,
        result: str,
        project_id: str | None = None,
        count: int | None = None,
    ) -> None:
        logger.info(
            "project_crud",
            extra={
                "action": action,
                "user_id": user_id,
                "project_id": project_id,
                "result": result,
                "count": count,
            },
        )
