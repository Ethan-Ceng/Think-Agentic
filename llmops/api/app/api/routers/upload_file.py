from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_upload_file_service
from app.core.exceptions import NotFoundException
from app.models.account import Account
from app.schemas.upload_file import UploadFileResponse
from app.services.upload_file_service import UploadFileService
from app.shared.response import success_json

router = APIRouter(prefix="/upload-files", tags=["upload_file"])


@router.post("")
def upload_file(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: UploadFileService = Depends(get_upload_file_service),
):
    upload_file_record = svc.upload_file(session, file, False, current_user)
    return success_json(UploadFileResponse.from_upload_file(upload_file_record).model_dump())


@router.post("/images")
def upload_image(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: UploadFileService = Depends(get_upload_file_service),
):
    upload_file_record = svc.upload_file(session, file, True, current_user)
    return success_json({"image_url": svc.get_file_url_for_record(session, upload_file_record)})


@router.get("/{file_path:path}")
def get_uploaded_file(file_path: str, request: Request):
    root = Path(request.app.state.settings.local_storage_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    target = (root / file_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise NotFoundException("Upload file does not exist") from exc
    if not target.is_file():
        raise NotFoundException("Upload file does not exist")
    return FileResponse(target)
