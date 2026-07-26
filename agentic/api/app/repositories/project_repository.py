#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Project repository protocol."""
from typing import Protocol

from app.core.entities.project import Project


class ProjectRepository(Protocol):
    """User-scoped persistence for single-level Project directories."""

    async def list_by_user(self, user_id: str) -> list[Project]:
        ...

    async def get_by_id_for_user(
        self,
        project_id: str,
        user_id: str,
    ) -> Project | None:
        ...

    async def create(self, project: Project) -> Project:
        ...

    async def rename(
        self,
        project_id: str,
        user_id: str,
        name: str,
    ) -> Project:
        ...

    async def delete(self, project_id: str, user_id: str) -> None:
        ...
