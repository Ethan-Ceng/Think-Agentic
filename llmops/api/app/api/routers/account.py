from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_account_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.account import (
    GetCurrentUserResponse,
    UpdateAvatarRequest,
    UpdateNameRequest,
    UpdatePasswordRequest,
)
from app.services.account_service import AccountService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
def get_current_user_info(current_user: Account = Depends(get_current_account)):
    resp = GetCurrentUserResponse.from_account(current_user)
    return success_json(resp.model_dump())


@router.post("/password")
def update_password(
    req: UpdatePasswordRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    account_service: AccountService = Depends(get_account_service),
):
    account_service.update_password(session, req.password, current_user)
    return success_message("Update account password success")


@router.post("/name")
def update_name(
    req: UpdateNameRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    account_service: AccountService = Depends(get_account_service),
):
    account_service.update_account(session, current_user, name=req.name)
    return success_message("Update account name success")


@router.post("/avatar")
def update_avatar(
    req: UpdateAvatarRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    account_service: AccountService = Depends(get_account_service),
):
    account_service.update_account(session, current_user, avatar=str(req.avatar))
    return success_message("Update account avatar success")

