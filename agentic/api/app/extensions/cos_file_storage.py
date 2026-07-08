#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File storage implementation.

Uses Tencent COS when configured, otherwise falls back to local disk storage.
"""
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable, Tuple

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.extensions.file_storage import FileStorage
from app.core.entities.file import File
from app.extensions.storage import Storage as Cos
from app.repositories.uow import IUnitOfWork

logger = logging.getLogger(__name__)
LOCAL_STORAGE_PATH = Path("/app/storage/files")


class CosFileStorage(FileStorage):
    """COS-backed file storage with a local fallback."""

    def __init__(
        self,
        bucket: str,
        cos: Cos,
        uow_factory: Callable[[], IUnitOfWork],
    ) -> None:
        self.bucket = bucket
        self.cos = cos
        self._uow_factory = uow_factory

    def _use_cos(self) -> bool:
        return bool(self.bucket and self.cos.client_or_none is not None)

    async def upload_file(self, upload_file: UploadFile, user_id: str) -> File:
        file_id = str(uuid.uuid4())
        filename = upload_file.filename or f"{file_id}.bin"
        _, extension = os.path.splitext(filename)
        extension = extension.lstrip(".")

        if self._use_cos():
            date_path = datetime.now().strftime("%Y/%m/%d")
            key = f"{user_id}/{date_path}/{file_id}{'.' + extension if extension else ''}"
            filepath = ""
            await run_in_threadpool(
                self.cos.client.put_object,
                Bucket=self.bucket,
                Body=upload_file.file,
                Key=key,
            )
            size = upload_file.size or 0
        else:
            user_storage_path = LOCAL_STORAGE_PATH / user_id
            user_storage_path.mkdir(parents=True, exist_ok=True)
            key = f"{file_id}_{filename}"
            local_path = user_storage_path / key
            content = await upload_file.read()
            await run_in_threadpool(local_path.write_bytes, content)
            filepath = str(local_path)
            size = len(content)

        file = File(
            id=file_id,
            user_id=user_id,
            filename=filename,
            filepath=filepath,
            key=key,
            extension=extension,
            mime_type=upload_file.content_type or "",
            size=size,
        )
        uow = self._uow_factory()
        async with uow:
            await uow.file.save(file)

        logger.info("File uploaded: %s (ID: %s)", filename, file_id)
        return file

    async def download_file(self, file_id: str, user_id: str | None = None) -> Tuple[BinaryIO, File]:
        uow = self._uow_factory()
        async with uow:
            file = await (
                uow.file.get_by_id_for_user(file_id, user_id)
                if user_id
                else uow.file.get_by_id(file_id)
            )
        if not file:
            raise ValueError(f"File does not exist: {file_id}")

        if file.filepath:
            if not os.path.exists(file.filepath):
                raise FileNotFoundError(f"Local file does not exist: {file.filepath}")
            return open(file.filepath, "rb"), file

        response = await run_in_threadpool(
            self.cos.client.get_object,
            Bucket=self.bucket,
            Key=file.key,
        )
        return response["Body"], file
