from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi import File as FastAPIFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_file_service
from app.core.exceptions import ValidateErrorException
from app.models.account import Account
from app.schemas.file import FileBatchDeleteRequest, FileBatchMoveRequest, FileCreateFolderRequest, FileUpdateRequest
from app.services.file_service import FileService
from app.shared.response import success_json

router = APIRouter(prefix="/files", tags=["files"])


def _parse_optional_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"undefined", "null"}:
        return None
    try:
        return UUID(text)
    except ValueError as exc:
        raise ValidateErrorException("Parent id is invalid") from exc


def _clean_optional_query(value: str | None) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"undefined", "null"} else text


def _clean_choice(value: str | None, allowed: set[str], default: str) -> str:
    text = _clean_optional_query(value).lower()
    if not text:
        return default
    if text not in allowed:
        raise ValidateErrorException("File filter is invalid")
    return text


@router.get("/status")
async def files_status() -> dict[str, str]:
    return {"status": "ok"}


@router.get("")
def list_files(
    parent_id: str | None = None,
    search_word: str | None = "",
    file_kind: str | None = "all",
    source: str | None = "all",
    current_page: int | None = Query(default=None, ge=1, le=9999),
    page_size: int | None = Query(default=None, ge=1, le=100),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    parent_uuid = _parse_optional_uuid(parent_id)
    cleaned_search_word = _clean_optional_query(search_word)
    cleaned_file_kind = _clean_choice(file_kind, {"all", "image", "video", "audio", "document", "other"}, "all")
    cleaned_source = _clean_choice(source, {"all", "upload", "generated"}, "all")
    if current_page is not None or page_size is not None:
        page = current_page or 1
        size = page_size or 20
        files, total_record, total_page = svc.list_files_with_page(
            session,
            current_user,
            parent_id=parent_uuid,
            search_word=cleaned_search_word,
            file_kind=cleaned_file_kind,
            source_filter=cleaned_source,
            current_page=page,
            page_size=size,
        )
        return success_json(
            {
                "list": [svc.to_response(session, file) for file in files],
                "paginator": {
                    "total_page": total_page,
                    "total_record": total_record,
                    "current_page": page,
                    "page_size": size,
                },
            }
        )
    files = svc.list_files(
        session,
        current_user,
        parent_id=parent_uuid,
        search_word=cleaned_search_word,
        file_kind=cleaned_file_kind,
        source_filter=cleaned_source,
    )
    return success_json([svc.to_response(session, file) for file in files])


@router.get("/folders/tree")
def list_folder_tree(
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    return success_json(svc.list_folder_tree(session, current_user))


@router.post("/folders")
def create_folder(
    req: FileCreateFolderRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    folder = svc.create_folder(session, current_user, req.name, req.parent_id)
    return success_json(svc.to_response(session, folder))


@router.post("/upload")
def upload_file(
    parent_id: str | None = None,
    file: UploadFile = FastAPIFile(...),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.upload(session, current_user, file, parent_id=_parse_optional_uuid(parent_id))
    return success_json(svc.to_response(session, stored_file))


@router.post("/batch-move")
def batch_move_files(
    req: FileBatchMoveRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    files = svc.move_files(session, current_user, req.file_ids, req.parent_id)
    return success_json([svc.to_response(session, file) for file in files])


@router.post("/batch-delete")
def batch_delete_files(
    req: FileBatchDeleteRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    files = svc.delete_files(session, current_user, req.file_ids)
    return success_json([svc.to_response(session, file) for file in files])


@router.get("/{file_id}")
def get_file(
    file_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.get_file(session, current_user, file_id)
    return success_json(svc.to_response(session, stored_file))


@router.patch("/{file_id}")
def update_file(
    file_id: UUID,
    req: FileUpdateRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.get_file(session, current_user, file_id)
    if req.name is not None:
        stored_file = svc.rename_file(session, current_user, file_id, req.name)
    if "parent_id" in req.model_fields_set:
        stored_file = svc.move_file(session, current_user, file_id, req.parent_id)
    return success_json(svc.to_response(session, stored_file))


@router.delete("/{file_id}")
def delete_file(
    file_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.delete_file(session, current_user, file_id)
    return success_json(svc.to_response(session, stored_file))


@router.get("/{file_id}/download")
def get_download_url(
    file_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.get_file(session, current_user, file_id)
    return success_json({"url": svc.to_response(session, stored_file)["download_url"]})
