import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from fastapi import UploadFile as FastAPIUploadFile
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import FailException, NotFoundException
from app.models.account import Account
from app.models.file import File
from app.services.base_service import BaseService
from app.services.storage_service import StorageService
from app.services.upload_file_service import UploadFileService


@dataclass
class FileService(BaseService):
    upload_file_service: UploadFileService = field(default_factory=UploadFileService)
    storage_service: StorageService = field(default_factory=StorageService)
    agent_input_preview_bytes: int = 64 * 1024

    def list_files(
        self,
        session: Session,
        account: Account,
        parent_id: UUID | None = None,
        search_word: str = "",
        file_kind: str = "all",
        source_filter: str = "all",
    ) -> list[File]:
        return list(self._list_files_query(session, account, parent_id, search_word, file_kind, source_filter).all())

    def list_files_with_page(
        self,
        session: Session,
        account: Account,
        parent_id: UUID | None = None,
        search_word: str = "",
        file_kind: str = "all",
        source_filter: str = "all",
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[File], int, int]:
        query = self._list_files_query(session, account, parent_id, search_word, file_kind, source_filter)
        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        files = query.limit(page_size).offset((current_page - 1) * page_size).all()
        return list(files), total_record, total_page

    def list_folder_tree(self, session: Session, account: Account) -> list[dict]:
        folders = (
            session.query(File)
            .filter(
                File.account_id == account.id,
                File.type == "folder",
                File.status == "available",
            )
            .order_by(File.created_at.asc(), File.name.asc())
            .all()
        )
        children_by_parent: dict[UUID | None, list[File]] = {}
        for folder in folders:
            children_by_parent.setdefault(folder.parent_id, []).append(folder)

        result: list[dict] = []

        def visit(parent_id: UUID | None, depth: int) -> None:
            for folder in children_by_parent.get(parent_id, []):
                result.append(
                    {
                        "id": folder.id,
                        "parent_id": folder.parent_id,
                        "name": folder.name,
                        "depth": depth,
                    }
                )
                visit(folder.id, depth + 1)

        visit(None, 1)
        return result

    def _list_files_query(
        self,
        session: Session,
        account: Account,
        parent_id: UUID | None = None,
        search_word: str = "",
        file_kind: str = "all",
        source_filter: str = "all",
    ):
        query = session.query(File).filter(File.account_id == account.id, File.status == "available")
        if parent_id is None:
            query = query.filter(File.parent_id.is_(None))
        else:
            query = query.filter(File.parent_id == parent_id)
        if search_word:
            query = query.filter(File.name.ilike(f"%{search_word}%"))
        if source_filter == "upload":
            query = query.filter(File.source == "upload")
        elif source_filter == "generated":
            query = query.filter(File.type == "file", File.source != "upload")
        query = self._apply_kind_filter(query, file_kind)
        return query.order_by(File.type.desc(), desc(File.updated_at))

    def _apply_kind_filter(self, query, file_kind: str):
        if file_kind == "all":
            return query
        query = query.filter(File.type == "file")
        if file_kind == "image":
            return query.filter(self._kind_expr("image"))
        if file_kind == "video":
            return query.filter(self._kind_expr("video"))
        if file_kind == "audio":
            return query.filter(self._kind_expr("audio"))
        if file_kind == "document":
            return query.filter(self._kind_expr("document"))
        if file_kind == "other":
            known_expr = or_(
                self._kind_expr("image"),
                self._kind_expr("video"),
                self._kind_expr("audio"),
                self._kind_expr("document"),
            )
            return query.filter(~known_expr)
        return query

    @staticmethod
    def _kind_expr(file_kind: str):
        extension = func.lower(File.extension)
        if file_kind == "image":
            return or_(
                File.mime_type.ilike("image/%"),
                extension.in_(["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"]),
            )
        if file_kind == "video":
            return or_(File.mime_type.ilike("video/%"), extension.in_(["mp4", "webm", "mov", "m4v", "avi"]))
        if file_kind == "audio":
            return or_(File.mime_type.ilike("audio/%"), extension.in_(["mp3", "wav", "ogg", "m4a", "flac"]))
        if file_kind == "document":
            return extension.in_(["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "json"])
        return File.type == "file"

    def create_folder(self, session: Session, account: Account, name: str, parent_id: UUID | None = None) -> File:
        name = name.strip()
        if not name:
            raise FailException("Folder name is required")
        if parent_id:
            parent = self.get_file(session, account, parent_id)
            if parent.type != "folder":
                raise FailException("Parent must be a folder")
        return self.create(
            session,
            File,
            account_id=account.id,
            parent_id=parent_id,
            type="folder",
            name=name,
            source="upload",
            status="available",
            created_by=account.id,
        )

    def upload(
        self,
        session: Session,
        account: Account,
        file: FastAPIUploadFile,
        parent_id: UUID | None = None,
    ) -> File:
        if parent_id:
            parent = self.get_file(session, account, parent_id)
            if parent.type != "folder":
                raise FailException("Parent must be a folder")
        return self.upload_file_service.upload_file(
            session,
            file,
            False,
            account,
            parent_id=parent_id,
            validate_extension=False,
        )

    def get_file(self, session: Session, account: Account, file_id: UUID) -> File:
        file = self.get(session, File, file_id)
        if file is None or file.account_id != account.id or file.status == "deleted":
            raise NotFoundException("File does not exist")
        return file

    def to_agent_input_ref(self, session: Session, account: Account, file_id: UUID) -> dict:
        file = self.get_file(session, account, file_id)
        if file.type != "file":
            raise FailException("Agent input must be a file")
        data = self.to_response(session, file)
        data["file_id"] = str(file.id)
        if self._can_inline_text(file):
            try:
                content = self.storage_service.read(session, account.id, file.storage_provider, file.file_path)
                text = content[: self.agent_input_preview_bytes].decode("utf-8", errors="replace")
                data["content"] = text
                data["content_truncated"] = len(content) > self.agent_input_preview_bytes
            except (FailException, NotFoundException) as exc:
                data["content_unavailable_reason"] = str(exc)
        return data

    def create_agent_artifact(
        self,
        session: Session,
        account: Account,
        *,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain; charset=utf-8",
        extension: str = "txt",
        metadata: dict | None = None,
    ) -> File:
        filename = (name or "").strip() or "agent-artifact.txt"
        if "." not in filename and extension:
            filename = f"{filename}.{extension.lstrip('.')}"
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if not raw:
            raise FailException("Agent artifact content is empty")

        file_path = UploadFileService._build_storage_key(extension.lstrip(".") or "txt")
        stored = self.storage_service.save(session, account.id, file_path, raw)
        return self.create(
            session,
            File,
            account_id=account.id,
            parent_id=None,
            type="file",
            name=filename,
            file_path=stored.file_path,
            storage_provider=stored.storage_provider,
            size=len(raw),
            extension=extension.lstrip(".") or "txt",
            mime_type=mime_type,
            hash=hashlib.sha3_256(raw).hexdigest(),
            source="agent",
            status="available",
            meta=metadata or {},
            created_by=account.id,
        )

    def rename_file(self, session: Session, account: Account, file_id: UUID, name: str) -> File:
        name = name.strip()
        if not name:
            raise FailException("File name is required")
        return self.update(session, self.get_file(session, account, file_id), name=name)

    def move_file(self, session: Session, account: Account, file_id: UUID, parent_id: UUID | None) -> File:
        file = self.get_file(session, account, file_id)
        if parent_id == file.id:
            raise FailException("Cannot move file into itself")
        if parent_id:
            parent = self.get_file(session, account, parent_id)
            if parent.type != "folder":
                raise FailException("Parent must be a folder")
            if file.type == "folder":
                self._ensure_not_descendant(session, account, file, parent)
        return self.update(session, file, parent_id=parent_id)

    def move_files(
        self,
        session: Session,
        account: Account,
        file_ids: list[UUID],
        parent_id: UUID | None,
    ) -> list[File]:
        files = [self.move_file(session, account, file_id, parent_id) for file_id in file_ids]
        session.flush()
        return files

    def delete_file(self, session: Session, account: Account, file_id: UUID) -> File:
        file = self.get_file(session, account, file_id)
        deleted_at = datetime.now()
        for item in self._collect_descendants(session, account, file):
            item.status = "deleted"
            item.deleted_at = deleted_at
        session.flush()
        session.refresh(file)
        return file

    def delete_files(self, session: Session, account: Account, file_ids: list[UUID]) -> list[File]:
        targets = [self.get_file(session, account, file_id) for file_id in file_ids]
        deleted_at = datetime.now()
        deleted: list[File] = []
        seen: set[UUID] = set()
        for target in targets:
            for item in self._collect_descendants(session, account, target):
                if item.id in seen:
                    continue
                item.status = "deleted"
                item.deleted_at = deleted_at
                deleted.append(item)
                seen.add(item.id)
        session.flush()
        return targets

    def _ensure_not_descendant(self, session: Session, account: Account, source: File, target_parent: File) -> None:
        cursor: File | None = target_parent
        while cursor is not None:
            if cursor.id == source.id:
                raise FailException("Cannot move folder into its child folder")
            cursor = self.get_file(session, account, cursor.parent_id) if cursor.parent_id else None

    def _collect_descendants(self, session: Session, account: Account, file: File) -> list[File]:
        result = [file]
        queue = [file.id]
        while queue:
            parent_id = queue.pop(0)
            children = (
                session.query(File)
                .filter(
                    File.account_id == account.id,
                    File.parent_id == parent_id,
                    File.status != "deleted",
                )
                .all()
            )
            result.extend(children)
            queue.extend([child.id for child in children if child.type == "folder"])
        return result

    def to_response(self, session: Session, file: File) -> dict:
        url = ""
        if file.type == "file" and file.file_path:
            url = self.storage_service.absolute_url(session, file.account_id, file.storage_provider, file.file_path)
        return {
            "id": file.id,
            "account_id": file.account_id,
            "parent_id": file.parent_id,
            "type": file.type,
            "name": file.name,
            "extension": file.extension,
            "mime_type": file.mime_type,
            "size": file.size,
            "storage_provider": file.storage_provider,
            "file_path": file.file_path,
            "hash": file.hash,
            "source": file.source,
            "status": file.status,
            "metadata": file.meta,
            "url": url,
            "download_url": url,
            "preview_url": url,
            "created_at": self._ts(file.created_at),
            "updated_at": self._ts(file.updated_at),
        }

    @staticmethod
    def _can_inline_text(file: File) -> bool:
        if file.size <= 0:
            return False
        if file.mime_type.startswith("text/"):
            return True
        return file.extension.lower() in {"txt", "md", "csv", "json", "yaml", "yml", "log"}

    @staticmethod
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0
