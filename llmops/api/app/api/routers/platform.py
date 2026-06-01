from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_platform_service
from app.models.account import Account
from app.schemas.platform import UpdateWechatConfigRequest, WechatConfigResponse
from app.services.platform_service import PlatformService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/apps/{app_id}/platforms", tags=["platform"])


@router.get("/wechat")
def get_wechat_config(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: PlatformService = Depends(get_platform_service),
):
    config = svc.get_wechat_config(session, app_id, current_user)
    return success_json(WechatConfigResponse.from_config(config).model_dump())


@router.put("/wechat")
def update_wechat_config(
    app_id: UUID,
    req: UpdateWechatConfigRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: PlatformService = Depends(get_platform_service),
):
    svc.update_wechat_config(
        session,
        app_id,
        current_user,
        req.wechat_app_id,
        req.wechat_app_secret,
        req.wechat_token,
    )
    return success_message("Update app wechat config success")
