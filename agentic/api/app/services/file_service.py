#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File service.
"""
import math
from datetime import datetime, timedelta
from typing import BinaryIO, Callable, Tuple

from fastapi import UploadFile

from app.extensions.file_storage import FileStorage
from app.core.entities.file import File
from app.repositories.uow import IUnitOfWork
from app.core.config import get_settings
from app.schemas.exceptions import BadRequestError, NotFoundError


class FileService:
    """MoocManus file service."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        file_storage: FileStorage,
    ) -> None:
        self.file_storage = file_storage
        self._uow_factory = uow_factory

    async def upload_file(self, upload_file: UploadFile, user_id: str, parent_id: str | None = None) -> File:
        """Upload a file and persist its metadata."""
        if parent_id:
            await self._require_folder(parent_id, user_id)
        return await self.file_storage.upload_file(upload_file=upload_file, user_id=user_id, parent_id=parent_id)

    async def get_file_info(self, file_id: str, user_id: str) -> File:
        """Get persisted file metadata."""
        uow = self._uow_factory()
        async with uow:
            file = await uow.file.get_by_id_for_user(file_id, user_id)
        if not file or file.status != "available":
            raise NotFoundError(f"File [{file_id}] does not exist")
        return file

    async def download_file(self, file_id: str, user_id: str) -> Tuple[BinaryIO, File]:
        """Download file content and return its metadata."""
        return await self.file_storage.download_file(file_id, user_id=user_id)

    async def list_files(self, user_id: str, *, parent_id: str | None = None, search_word: str = "", file_kind: str = "all", source_type: str = "all", current_page: int = 1, page_size: int = 20) -> dict:
        if parent_id:
            await self._require_folder(parent_id, user_id)
        uow = self._uow_factory()
        async with uow:
            files, total = await uow.file.list_for_user(
                user_id,
                parent_id=parent_id,
                search_word=search_word.strip(),
                file_kind=file_kind,
                source_type=source_type,
                offset=(current_page - 1) * page_size,
                limit=page_size,
            )
        return {
            "list": [self.to_response(file) for file in files],
            "paginator": {
                "current_page": current_page,
                "page_size": page_size,
                "total_record": total,
                "total_page": math.ceil(total / page_size) if total else 0,
            },
        }

    async def list_folder_tree(self, user_id: str) -> list[dict]:
        uow = self._uow_factory()
        async with uow:
            folders = await uow.file.list_folders_for_user(user_id)
        children: dict[str | None, list[File]] = {}
        for folder in folders:
            children.setdefault(folder.parent_id, []).append(folder)
        result: list[dict] = []

        def visit(parent_id: str | None, depth: int) -> None:
            for folder in children.get(parent_id, []):
                result.append({"id": folder.id, "parent_id": folder.parent_id, "name": folder.filename, "depth": depth})
                visit(folder.id, depth + 1)

        visit(None, 1)
        return result

    async def create_folder(self, user_id: str, name: str, parent_id: str | None = None) -> File:
        clean_name = name.strip()
        if not clean_name:
            raise BadRequestError("目录名称不能为空")
        if parent_id:
            await self._require_folder(parent_id, user_id)
        folder = File(user_id=user_id, filename=clean_name, parent_id=parent_id, entry_type="folder")
        uow = self._uow_factory()
        async with uow:
            await uow.file.save(folder)
        return folder

    async def rename_file(self, file_id: str, user_id: str, name: str) -> File:
        clean_name = name.strip()
        if not clean_name:
            raise BadRequestError("文件名称不能为空")
        file = await self.get_file_info(file_id, user_id)
        file.filename = clean_name
        if file.entry_type == "file":
            file.extension = clean_name.rsplit(".", 1)[-1].lower() if "." in clean_name else ""
        uow = self._uow_factory()
        async with uow:
            await uow.file.save(file)
        return file

    async def move_files(self, file_ids: list[str], user_id: str, parent_id: str | None) -> list[File]:
        target = await self._require_folder(parent_id, user_id) if parent_id else None
        files = [await self.get_file_info(file_id, user_id) for file_id in dict.fromkeys(file_ids)]
        if target:
            for file in files:
                await self._ensure_not_descendant(file, target, user_id)
        uow = self._uow_factory()
        async with uow:
            for file in files:
                file.parent_id = parent_id
                await uow.file.save(file)
        return files

    async def delete_files(self, file_ids: list[str], user_id: str) -> list[File]:
        settings = get_settings()
        deleted_at = datetime.now()
        purge_after = deleted_at + timedelta(days=settings.deleted_file_retention_days)
        targets = [await self.get_file_info(file_id, user_id) for file_id in dict.fromkeys(file_ids)]
        deleted: dict[str, File] = {}
        for target in targets:
            await self._collect_descendants(target, user_id, deleted)
        uow = self._uow_factory()
        async with uow:
            for file in deleted.values():
                file.status = "deleted"
                file.deleted_at = deleted_at
                file.purge_after = purge_after
                await uow.file.save(file)
        return targets

    async def _require_folder(self, file_id: str | None, user_id: str) -> File:
        if not file_id:
            raise BadRequestError("目录 ID 不能为空")
        file = await self.get_file_info(file_id, user_id)
        if file.entry_type != "folder":
            raise BadRequestError("目标必须是目录")
        return file

    async def _ensure_not_descendant(self, source: File, target: File, user_id: str) -> None:
        cursor: File | None = target
        while cursor:
            if cursor.id == source.id:
                raise BadRequestError("不能将目录移动到自身或其子目录")
            cursor = await self.get_file_info(cursor.parent_id, user_id) if cursor.parent_id else None

    async def _collect_descendants(self, file: File, user_id: str, result: dict[str, File]) -> None:
        if file.id in result:
            return
        result[file.id] = file
        if file.entry_type != "folder":
            return
        uow = self._uow_factory()
        async with uow:
            children = await uow.file.list_children(user_id, file.id)
        for child in children:
            await self._collect_descendants(child, user_id, result)

    @staticmethod
    def to_response(file: File) -> dict:
        return {
            "id": file.id,
            "parent_id": file.parent_id,
            "type": file.entry_type,
            "name": file.filename,
            "filename": file.filename,
            "extension": file.extension,
            "mime_type": file.mime_type,
            "content_type": file.mime_type,
            "size": file.size,
            "storage_provider": file.storage_provider,
            "source_type": file.source_type,
            "status": file.status,
            "sha256": file.sha256,
            "origin_session_id": file.origin_session_id,
            "origin_run_id": file.origin_run_id,
            "metadata": file.metadata,
            "url": f"/api/files/{file.id}/preview" if file.entry_type == "file" else "",
            "download_url": f"/api/files/{file.id}/download" if file.entry_type == "file" else "",
            "preview_url": f"/api/files/{file.id}/preview" if file.entry_type == "file" else "",
            "created_at": int(file.created_at.timestamp()),
            "updated_at": int(file.updated_at.timestamp()),
        }
