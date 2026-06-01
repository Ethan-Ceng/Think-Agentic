from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_account_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.auth import PasswordLoginRequest
from app.services.account_service import AccountService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/password-login")
def password_login(
    req: PasswordLoginRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    account_service: AccountService = Depends(get_account_service),
):
    credential = account_service.password_login(
        session,
        req.email,
        req.password,
        request.client.host if request.client else "unknown",
    )
    return success_json(credential)


@router.post("/logout")
def logout(_: Account = Depends(get_current_account)):
    return success_message("Logout success")

