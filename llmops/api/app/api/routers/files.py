from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from fastapi import File as FastAPIFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_file_service
from app.models.account import Account
from app.schemas.file import FileCreateFolderRequest, FileUpdateRequest
from app.services.file_service import FileService
from app.shared.response import success_json

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/status")
async def files_status() -> dict[str, str]:
    return {"status": "ok"}


@router.get("")
def list_files(
    parent_id: UUID | None = None,
    search_word: str = "",
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    files = svc.list_files(session, current_user, parent_id=parent_id, search_word=search_word)
    return success_json([svc.to_response(session, file) for file in files])


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
    parent_id: UUID | None = None,
    file: UploadFile = FastAPIFile(...),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: FileService = Depends(get_file_service),
):
    stored_file = svc.upload(session, current_user, file, parent_id=parent_id)
    return success_json(svc.to_response(session, stored_file))


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
    stored_file = svc.rename_file(session, current_user, file_id, req.name)
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
