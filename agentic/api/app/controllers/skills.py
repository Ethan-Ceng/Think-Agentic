"""Authenticated personal Skill and draft management routes."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.entities.user import User
from app.dependencies import get_current_user, get_skill_service
from app.schemas import Response
from app.schemas.skill import (
    PublishedSkillResponse,
    SkillAutoInvokeRequest,
    SkillDetailResponse,
    SkillDraftCreateRequest,
    SkillDraftFileWriteRequest,
    SkillDraftPublishRequest,
    SkillResponse,
    SkillUpdateRequest,
)
from app.services.skill_service import SkillService


skills_router = APIRouter(prefix="/skills", tags=["Skills"])
drafts_router = APIRouter(prefix="/skill-drafts", tags=["Skill 草稿"])


def _published_response(published) -> PublishedSkillResponse:
    return PublishedSkillResponse(
        skill=SkillResponse.model_validate(published.skill),
        version=published.version,
    )


def _detail_response(detail) -> SkillDetailResponse:
    return SkillDetailResponse(
        skill=SkillResponse.model_validate(detail.skill),
        version=detail.version,
    )


@skills_router.get("", summary="获取个人 Skills")
async def list_skills(
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[list[SkillResponse]]:
    skills = await service.list_skills(current_user.id)
    return Response.success(
        data=[SkillResponse.model_validate(skill) for skill in skills]
    )


@skills_router.post("/import", summary="导入标准 Skill 包")
async def import_skill(
    file: UploadFile = File(...),
    display_name: str | None = Form(default=None),
    changelog: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[PublishedSkillResponse]:
    published = await service.import_archive(
        current_user.id,
        file.file,
        display_name=display_name,
        changelog=changelog,
    )
    return Response.success(msg="Skill 导入成功", data=_published_response(published))


@skills_router.get("/{skill_id}", summary="获取个人 Skill")
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[SkillDetailResponse]:
    return Response.success(
        data=_detail_response(await service.get_skill(current_user.id, skill_id))
    )


@skills_router.patch("/{skill_id}", summary="更新个人 Skill")
async def update_skill(
    skill_id: str,
    body: SkillUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[SkillDetailResponse]:
    detail = await service.update_skill(
        current_user.id,
        skill_id,
        display_name=body.display_name,
        description=body.description,
    )
    return Response.success(msg="Skill 更新成功", data=_detail_response(detail))


@skills_router.delete("/{skill_id}", summary="归档个人 Skill")
async def archive_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    await service.archive_skill(current_user.id, skill_id)
    return Response.success(msg="Skill 已归档")


@skills_router.post("/{skill_id}/enable", summary="启用个人 Skill")
async def enable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[SkillDetailResponse]:
    return Response.success(
        data=_detail_response(
            await service.set_enabled(current_user.id, skill_id, True)
        )
    )


@skills_router.post("/{skill_id}/disable", summary="停用个人 Skill")
async def disable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[SkillDetailResponse]:
    return Response.success(
        data=_detail_response(
            await service.set_enabled(current_user.id, skill_id, False)
        )
    )


@skills_router.post("/{skill_id}/auto-invoke", summary="设置自动触发")
async def set_auto_invoke(
    skill_id: str,
    body: SkillAutoInvokeRequest,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[SkillDetailResponse]:
    return Response.success(
        data=_detail_response(
            await service.set_auto_invoke(
                current_user.id, skill_id, body.enabled
            )
        )
    )


@drafts_router.post("", summary="创建 Skill 草稿")
async def create_draft(
    body: SkillDraftCreateRequest,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    draft = await service.create_draft(
        current_user.id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
    )
    return Response.success(data=asdict(draft))


@drafts_router.get("/{draft_id}/tree", summary="获取 Skill 草稿目录树")
async def list_draft_tree(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    entries = await service.list_draft_tree(current_user.id, draft_id)
    validation = await service.validate_draft(current_user.id, draft_id)
    return Response.success(
        data={
            "tree": [asdict(entry) for entry in entries],
            "revision": validation.revision,
        }
    )


@drafts_router.get("/{draft_id}/files/{path:path}", summary="读取 Skill 草稿文件")
async def read_draft_file(
    draft_id: str,
    path: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    content = await service.read_draft_file(current_user.id, draft_id, path)
    return Response.success(data={"path": path, "content": content})


@drafts_router.put("/{draft_id}/files/{path:path}", summary="写入 Skill 草稿文件")
async def write_draft_file(
    draft_id: str,
    path: str,
    body: SkillDraftFileWriteRequest,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    await service.write_draft_file(current_user.id, draft_id, path, body.content)
    return Response.success(msg="Skill 草稿文件已保存", data={"path": path})


@drafts_router.post("/{draft_id}/validate", summary="校验 Skill 草稿")
async def validate_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[dict]:
    result = await service.validate_draft(current_user.id, draft_id)
    return Response.success(data=asdict(result))


@drafts_router.post("/{draft_id}/publish", summary="发布 Skill 草稿")
async def publish_draft(
    draft_id: str,
    body: SkillDraftPublishRequest,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response[PublishedSkillResponse]:
    published = await service.publish_draft(
        current_user.id,
        draft_id,
        expected_revision=body.expected_revision,
        changelog=body.changelog,
    )
    return Response.success(msg="Skill 发布成功", data=_published_response(published))
