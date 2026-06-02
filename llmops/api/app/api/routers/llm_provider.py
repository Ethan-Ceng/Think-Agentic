from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_llm_provider_service
from app.models.account import Account
from app.schemas.llm_provider import (
    LLMModelCreateRequest,
    LLMModelUpdateRequest,
    LLMProviderCreateRequest,
    LLMProviderUpdateRequest,
)
from app.services.llm_provider_service import LLMProviderService
from app.shared.response import success_json

router = APIRouter(prefix="/llm-providers", tags=["llm_provider"])


@router.get("")
def list_llm_providers(
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    providers = svc.list_providers(session, current_user.id)
    return success_json([svc.serialize_provider(session, provider) for provider in providers])


@router.post("")
def create_llm_provider(
    req: LLMProviderCreateRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    provider = svc.create_provider(session, current_user.id, **req.model_dump())
    return success_json(svc.serialize_provider(session, provider))


@router.patch("/{provider_id}")
def update_llm_provider(
    provider_id: UUID,
    req: LLMProviderUpdateRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    provider = svc.update_provider(
        session,
        current_user.id,
        provider_id,
        **req.model_dump(exclude_unset=True),
    )
    return success_json(svc.serialize_provider(session, provider))


@router.delete("/{provider_id}")
def delete_llm_provider(
    provider_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    provider = svc.delete_provider(session, current_user.id, provider_id)
    return success_json(svc.serialize_provider(session, provider, include_models=False))


@router.post("/{provider_id}/models")
def create_llm_model(
    provider_id: UUID,
    req: LLMModelCreateRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    model = svc.create_model(session, current_user.id, provider_id, **req.model_dump())
    return success_json(svc.serialize_model(model))


@router.patch("/{provider_id}/models/{model_id}")
def update_llm_model(
    provider_id: UUID,
    model_id: UUID,
    req: LLMModelUpdateRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    model = svc.update_model(
        session,
        current_user.id,
        provider_id,
        model_id,
        **req.model_dump(exclude_unset=True),
    )
    return success_json(svc.serialize_model(model))


@router.delete("/{provider_id}/models/{model_id}")
def delete_llm_model(
    provider_id: UUID,
    model_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: LLMProviderService = Depends(get_llm_provider_service),
):
    model = svc.delete_model(session, current_user.id, provider_id, model_id)
    return success_json(svc.serialize_model(model))
