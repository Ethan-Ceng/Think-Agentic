from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_setting_service
from app.models.account import Account
from app.schemas.setting import SettingUpsertRequest
from app.services.setting_service import SettingService
from app.shared.response import success_json

router = APIRouter(prefix="/settings", tags=["setting"])


@router.get("")
def list_settings(
    category: str | None = None,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SettingService = Depends(get_setting_service),
):
    settings = svc.list_settings(session, current_user.id, category)
    return success_json([svc.serialize_setting(setting) for setting in settings])


@router.get("/{category}")
def list_category_settings(
    category: str,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SettingService = Depends(get_setting_service),
):
    settings = svc.list_settings(session, current_user.id, category)
    return success_json([svc.serialize_setting(setting) for setting in settings])


@router.get("/{category}/{key}")
def get_setting(
    category: str,
    key: str,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SettingService = Depends(get_setting_service),
):
    setting = svc.get_setting(session, current_user.id, category, key)
    return success_json(svc.serialize_setting(setting))


@router.put("/{category}/{key}")
def upsert_setting(
    category: str,
    key: str,
    req: SettingUpsertRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SettingService = Depends(get_setting_service),
):
    setting = svc.upsert_setting(session, current_user.id, category, key, req.value, req.enabled)
    return success_json(svc.serialize_setting(setting))
