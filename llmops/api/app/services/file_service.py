from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from fastapi import UploadFile as FastAPIUploadFile
from sqlalchemy import desc
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

    def list_files(
        self,
        session: Session,
        account: Account,
        parent_id: UUID | None = None,
        search_word: str = "",
    ) -> list[File]:
        query = session.query(File).filter(File.account_id == account.id, File.status == "available")
        if parent_id is None:
            query = query.filter(File.parent_id.is_(None))
        else:
            query = query.filter(File.parent_id == parent_id)
        if search_word:
            query = query.filter(File.name.ilike(f"%{search_word}%"))
        return list(query.order_by(File.type.desc(), desc(File.updated_at)).all())

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

    def delete_file(self, session: Session, account: Account, file_id: UUID) -> File:
        file = self.get_file(session, account, file_id)
        deleted_at = datetime.now()
        for item in self._collect_descendants(session, account, file):
            item.status = "deleted"
            item.deleted_at = deleted_at
        session.flush()
        session.refresh(file)
        return file

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
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0
