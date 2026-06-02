import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.file import File
from app.services.storage_service import StorageService
from app.services.upload_file_service import UploadFileService


@dataclass
class FileExtractor:
    """Local-storage first file extractor for the migration runtime."""

    storage_service: StorageService = field(default_factory=StorageService)

    def load(self, session: Session, upload_file: File) -> str:
        content = self.storage_service.read(
            session,
            upload_file.account_id,
            upload_file.storage_provider,
            upload_file.file_path,
        )
        return self.load_from_bytes(content, upload_file.extension)

    def load_legacy_local(self, upload_file: File) -> str:
        file_path = UploadFileService.get_local_file_path(upload_file.key)
        return self.load_from_file(file_path)

    @classmethod
    def load_from_file(cls, file_path: str) -> str:
        path = Path(file_path)
        content = path.read_bytes()
        text = cls._decode_bytes(content)
        if path.suffix.lower() in {".html", ".htm"}:
            text = cls._strip_html(text)
        return cls._clean_text(text)

    @classmethod
    def load_from_bytes(cls, content: bytes, extension: str = "") -> str:
        text = cls._decode_bytes(content)
        if extension.lower().lstrip(".") in {"html", "htm"}:
            text = cls._strip_html(text)
        return cls._clean_text(text)

    @staticmethod
    def _decode_bytes(content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return text

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"<\|", "<", text)
        text = re.sub(r"\|>", ">", text)
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
