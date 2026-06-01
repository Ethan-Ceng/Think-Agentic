from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_builtin_app_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.builtin_app import AddBuiltinAppRequest
from app.services.builtin_app_service import BuiltinAppService
from app.shared.response import success_json

router = APIRouter(prefix="/builtin-apps", tags=["builtin_app"])


@router.get("/categories")
def get_builtin_app_categories(
    _: Account = Depends(get_current_account),
    svc: BuiltinAppService = Depends(get_builtin_app_service),
):
    return success_json([category.model_dump() for category in svc.get_categories()])


@router.get("")
def get_builtin_apps(
    _: Account = Depends(get_current_account),
    svc: BuiltinAppService = Depends(get_builtin_app_service),
):
    return success_json(
        [
            {
                **app.model_dump(include={"id", "category", "name", "icon", "description", "created_at"}),
                "model_config": {
                    "provider": app.language_model_config.get("provider", ""),
                    "model": app.language_model_config.get("model", ""),
                },
            }
            for app in svc.get_builtin_apps()
        ]
    )


@router.post("")
def add_builtin_app_to_space(
    req: AddBuiltinAppRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: BuiltinAppService = Depends(get_builtin_app_service),
):
    app = svc.add_builtin_app_to_space(session, str(req.builtin_app_id), current_user)
    return success_json({"id": app.id})
