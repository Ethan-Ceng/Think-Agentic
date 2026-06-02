import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from fastapi import UploadFile as FastAPIUploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dataset import ALLOWED_DOCUMENT_EXTENSION, ALLOWED_IMAGE_EXTENSION
from app.core.exceptions import FailException
from app.models.account import Account
from app.models.file import File
from app.services.base_service import BaseService
from app.services.storage_service import StorageService


@dataclass
class UploadFileService(BaseService):
    storage_service: StorageService = field(default_factory=StorageService)

    def upload_file(
        self,
        session: Session,
        file: FastAPIUploadFile,
        only_image: bool,
        account: Account,
        parent_id: UUID | None = None,
        source: str = "upload",
        validate_extension: bool = True,
    ) -> File:
        filename = file.filename or ""
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        allowed_extensions = ALLOWED_IMAGE_EXTENSION if only_image else ALLOWED_DOCUMENT_EXTENSION
        if validate_extension and extension not in allowed_extensions:
            raise FailException(f"Unsupported file extension: .{extension}")

        content = file.file.read()
        if not content:
            raise FailException("Uploaded file is empty")

        file_path = self._build_storage_key(extension)
        stored = self.storage_service.save(session, account.id, file_path, content)
        return self.create(
            session,
            File,
            account_id=account.id,
            parent_id=parent_id,
            type="file",
            name=filename,
            file_path=stored.file_path,
            storage_provider=stored.storage_provider,
            size=len(content),
            extension=extension,
            mime_type=file.content_type or "",
            hash=hashlib.sha3_256(content).hexdigest(),
            source=source,
            status="available",
            created_by=account.id,
        )

    @classmethod
    def get_file_url(cls, key: str) -> str:
        base_url = get_settings().local_storage_base_url
        return f"{base_url.rstrip('/')}/{key}"

    def get_file_url_for_record(self, session: Session, upload_file: File) -> str:
        return self.storage_service.absolute_url(
            session,
            upload_file.account_id,
            upload_file.storage_provider,
            upload_file.file_path,
        )

    @classmethod
    def get_local_file_path(cls, key: str) -> str:
        return os.path.join(cls._get_local_storage_root(), key.replace("\\", "/").lstrip("/"))

    @classmethod
    def _build_storage_key(cls, extension: str) -> str:
        now = datetime.now()
        return f"{now.year}/{now.month:02d}/{now.day:02d}/{uuid.uuid4()}.{extension}"

    @classmethod
    def _get_local_storage_root(cls) -> str:
        return StorageService.legacy_local_root()

    @classmethod
    def _save_local_file(cls, key: str, content: bytes) -> None:
        target_path = cls.get_local_file_path(key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as file:
            file.write(content)

