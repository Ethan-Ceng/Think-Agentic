#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/21 0:49
@Author  : thezehui@gmail.com
@File    : db_file_repository.py
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.file import File
from app.repositories.file_repository import FileRepository
from app.models import FileModel


class DBFileRepository(FileRepository):
    """基于数据库的文件数据仓库"""

    def __init__(self, db_session: AsyncSession) -> None:
        """构造函数，完成数据仓库初始化"""
        self.db_session = db_session

    async def save(self, file: File) -> None:
        """根据传递的文件模型存储or更新数据"""
        # 1.根据id查询记录是否存在
        stmt = select(FileModel).where(FileModel.id == file.id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        # 2.判断如果文件不存在则新建文件
        if not record:
            record = FileModel.from_domain(file)
            self.db_session.add(record)
            return

        # 3.文件存在则直接更新文件
        record.update_from_domain(file)

    async def get_by_id(self, file_id: str) -> Optional[File]:
        """根据传递的文件id获取文件信息"""
        # 1.根据id查询记录是否存在
        stmt = select(FileModel).where(FileModel.id == file_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        # 2.判断文件记录是否存在返回不同的值
        return record.to_domain() if record is not None else None

    async def get_by_id_for_user(self, file_id: str, user_id: str) -> Optional[File]:
        """根据传递的文件id和用户id获取文件信息"""
        stmt = select(FileModel).where(
            FileModel.id == file_id,
            FileModel.user_id == user_id,
        )
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def list_for_user(
        self,
        user_id: str,
        *,
        parent_id: str | None,
        search_word: str = "",
        file_kind: str = "all",
        source_type: str = "all",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[File], int]:
        filters = [
            FileModel.user_id == user_id,
            FileModel.status == "available",
            or_(FileModel.file_metadata["visible"].astext.is_(None), FileModel.file_metadata["visible"].astext != "false"),
        ]
        filters.append(FileModel.parent_id.is_(None) if parent_id is None else FileModel.parent_id == parent_id)
        if search_word:
            filters.append(FileModel.filename.ilike(f"%{search_word}%"))
        if source_type != "all":
            filters.append(FileModel.source_type == source_type)
        if file_kind != "all":
            filters.append(FileModel.entry_type == "file")
            filters.append(self._kind_filter(file_kind))

        count_stmt = select(func.count()).select_from(FileModel).where(*filters)
        total = int((await self.db_session.execute(count_stmt)).scalar_one())
        stmt = (
            select(FileModel)
            .where(*filters)
            .order_by(FileModel.entry_type.desc(), FileModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records], total

    @staticmethod
    def _kind_filter(file_kind: str):
        extension = func.lower(FileModel.extension)
        if file_kind == "image":
            return or_(FileModel.mime_type.ilike("image/%"), extension.in_(["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"]))
        if file_kind == "video":
            return or_(FileModel.mime_type.ilike("video/%"), extension.in_(["mp4", "webm", "mov", "m4v", "avi"]))
        if file_kind == "audio":
            return or_(FileModel.mime_type.ilike("audio/%"), extension.in_(["mp3", "wav", "ogg", "m4a", "flac"]))
        if file_kind == "document":
            return extension.in_(["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "json"])
        if file_kind == "other":
            known = ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "mp4", "webm", "mov", "m4v", "avi", "mp3", "wav", "ogg", "m4a", "flac", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "json"]
            return ~extension.in_(known)
        return FileModel.entry_type == "file"

    async def list_folders_for_user(self, user_id: str) -> list[File]:
        stmt = (
            select(FileModel)
            .where(FileModel.user_id == user_id, FileModel.entry_type == "folder", FileModel.status == "available")
            .order_by(FileModel.created_at.asc(), FileModel.filename.asc())
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def list_children(self, user_id: str, parent_id: str) -> list[File]:
        stmt = select(FileModel).where(
            FileModel.user_id == user_id,
            FileModel.parent_id == parent_id,
            FileModel.status == "available",
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def list_expired(self, now: datetime, limit: int = 100) -> list[File]:
        stmt = (
            select(FileModel)
            .where(FileModel.status == "deleted", FileModel.purge_after.is_not(None), FileModel.purge_after <= now)
            .order_by(FileModel.purge_after.asc())
            .limit(limit)
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def hard_delete(self, file_id: str) -> None:
        record = await self.db_session.get(FileModel, file_id)
        if record is not None:
            await self.db_session.delete(record)
