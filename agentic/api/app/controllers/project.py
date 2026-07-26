#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Authenticated Project directory CRUD routes."""
from fastapi import APIRouter, Depends

from app.core.entities.user import User
from app.dependencies import get_current_user, get_project_service
from app.schemas import Response
from app.schemas.project import (
    CreateProjectRequest,
    ProjectListResponse,
    ProjectResponse,
    RenameProjectRequest,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["项目管理"])


@router.get("", summary="获取项目列表")
async def list_projects(
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Response[ProjectListResponse]:
    projects = await service.list_projects(current_user.id)
    return Response.success(
        msg="获取项目列表成功",
        data=ProjectListResponse(
            projects=[
                ProjectResponse.model_validate(project)
                for project in projects
            ]
        ),
    )


@router.post("", summary="创建项目")
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Response[ProjectResponse]:
    project = await service.create_project(current_user.id, request.name)
    return Response.success(
        msg="创建项目成功",
        data=ProjectResponse.model_validate(project),
    )


@router.patch("/{project_id}", summary="重命名项目")
async def rename_project(
    project_id: str,
    request: RenameProjectRequest,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Response[ProjectResponse]:
    project = await service.rename_project(
        project_id,
        current_user.id,
        request.name,
    )
    return Response.success(
        msg="重命名项目成功",
        data=ProjectResponse.model_validate(project),
    )


@router.delete("/{project_id}", summary="删除项目")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> Response[dict]:
    await service.delete_project(project_id, current_user.id)
    return Response.success(msg="删除项目成功")
