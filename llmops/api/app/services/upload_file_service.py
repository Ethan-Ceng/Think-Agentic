import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import UploadFile as FastAPIUploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dataset import ALLOWED_DOCUMENT_EXTENSION, ALLOWED_IMAGE_EXTENSION
from app.core.exceptions import FailException
from app.models.account import Account
from app.models.upload_file import UploadFile
from app.services.base_service import BaseService


@dataclass
class UploadFileService(BaseService):
    def upload_file(
        self,
        session: Session,
        file: FastAPIUploadFile,
        only_image: bool,
        account: Account,
    ) -> UploadFile:
        filename = file.filename or ""
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        allowed_extensions = ALLOWED_IMAGE_EXTENSION if only_image else ALLOWED_DOCUMENT_EXTENSION
        if extension not in allowed_extensions:
            raise FailException(f"Unsupported file extension: .{extension}")

        content = file.file.read()
        if not content:
            raise FailException("Uploaded file is empty")

        key = self._build_storage_key(extension)
        self._save_local_file(key, content)
        return self.create(
            session,
            UploadFile,
            account_id=account.id,
            name=filename,
            key=key,
            size=len(content),
            extension=extension,
            mime_type=file.content_type or "",
            hash=hashlib.sha3_256(content).hexdigest(),
        )

    @classmethod
    def get_file_url(cls, key: str) -> str:
        base_url = get_settings().local_storage_base_url
        return f"{base_url.rstrip('/')}/{key}"

    @classmethod
    def get_local_file_path(cls, key: str) -> str:
        return os.path.join(cls._get_local_storage_root(), key)

    @classmethod
    def _build_storage_key(cls, extension: str) -> str:
        now = datetime.now()
        return f"{now.year}/{now.month:02d}/{now.day:02d}/{uuid.uuid4()}.{extension}"

    @classmethod
    def _get_local_storage_root(cls) -> str:
        root = get_settings().local_storage_root
        return root if os.path.isabs(root) else os.path.join(os.getcwd(), root)

    @classmethod
    def _save_local_file(cls, key: str, content: bytes) -> None:
        target_path = cls.get_local_file_path(key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as file:
            file.write(content)

