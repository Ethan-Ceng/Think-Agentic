#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File service.
"""
from typing import BinaryIO, Callable, Tuple

from fastapi import UploadFile

from app.extensions.file_storage import FileStorage
from app.core.entities.file import File
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import NotFoundError


class FileService:
    """MoocManus file service."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        file_storage: FileStorage,
    ) -> None:
        self.file_storage = file_storage
        self._uow_factory = uow_factory

    async def upload_file(self, upload_file: UploadFile, user_id: str) -> File:
        """Upload a file and persist its metadata."""
        return await self.file_storage.upload_file(upload_file=upload_file, user_id=user_id)

    async def get_file_info(self, file_id: str, user_id: str) -> File:
        """Get persisted file metadata."""
        uow = self._uow_factory()
        async with uow:
            file = await uow.file.get_by_id_for_user(file_id, user_id)
        if not file:
            raise NotFoundError(f"File [{file_id}] does not exist")
        return file

    async def download_file(self, file_id: str, user_id: str) -> Tuple[BinaryIO, File]:
        """Download file content and return its metadata."""
        return await self.file_storage.download_file(file_id, user_id=user_id)
