from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.api_key import (
    ApiKeyResponse,
    CreateApiKeyRequest,
    UpdateApiKeyIsActiveRequest,
    UpdateApiKeyRequest,
)
from app.services.api_key_service import ApiKeyService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/openapi/api-keys", tags=["api_key"])


@router.get("")
def get_api_keys(
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
):
    api_keys, total_record, total_page = api_key_service.get_api_keys_with_page(
        session,
        current_user,
        current_page,
        page_size,
    )
    return success_json(
        {
            "list": [ApiKeyResponse.from_api_key(api_key).model_dump() for api_key in api_keys],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_api_key(
    req: CreateApiKeyRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
):
    api_key_service.create_api_key(session, current_user, req.is_active, req.remark)
    return success_message("Create API key success")


@router.put("/{api_key_id}")
def update_api_key(
    api_key_id: UUID,
    req: UpdateApiKeyRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
):
    api_key_service.update_api_key(session, api_key_id, current_user, is_active=req.is_active, remark=req.remark)
    return success_message("Update API key success")


@router.patch("/{api_key_id}/is-active")
def update_api_key_is_active(
    api_key_id: UUID,
    req: UpdateApiKeyIsActiveRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
):
    api_key_service.update_api_key(session, api_key_id, current_user, is_active=req.is_active)
    return success_message("Update API key active status success")


@router.delete("/{api_key_id}")
def delete_api_key(
    api_key_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
):
    api_key_service.delete_api_key(session, api_key_id, current_user)
    return success_message("Delete API key success")

