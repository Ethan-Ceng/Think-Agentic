from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_audio_service, get_current_account, get_db_session
from app.core.exceptions import FailException
from app.models.account import Account
from app.schemas.audio import MessageToAudioRequest
from app.services.audio_service import AudioService
from app.shared.response import compact_generate_response, success_json

router = APIRouter(prefix="/audio", tags=["audio"])

ALLOWED_AUDIO = {"webm", "wav"}
MAX_AUDIO_SIZE = 25 * 1024 * 1024


@router.post("/to-text")
async def audio_to_text(
    file: UploadFile = File(...),
    _: Account = Depends(get_current_account),
    svc: AudioService = Depends(get_audio_service),
):
    ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "").lower()
    if ext not in ALLOWED_AUDIO:
        raise FailException(f"Please upload a valid audio file ({'/'.join(sorted(ALLOWED_AUDIO))})")
    content = await file.read()
    if len(content) > MAX_AUDIO_SIZE:
        raise FailException("Audio file must not exceed 25MB")
    text = svc.audio_to_text(file.filename or "recording.wav", content, file.content_type)
    return success_json({"text": text})


@router.post("/message-to-audio")
def message_to_audio(
    req: MessageToAudioRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AudioService = Depends(get_audio_service),
):
    return compact_generate_response(svc.message_to_audio(session, req.message_id, current_user))
