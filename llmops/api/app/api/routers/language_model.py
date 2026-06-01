import io

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import get_current_account, get_language_model_service
from app.models.account import Account
from app.schemas.language_model import LanguageModelResponse, LanguageModelsResponse
from app.services.language_model_service import LanguageModelService
from app.shared.response import success_json

router = APIRouter(prefix="/language-models", tags=["language_model"])


@router.get("", response_model=LanguageModelsResponse)
def get_language_models(
    _: Account = Depends(get_current_account),
    svc: LanguageModelService = Depends(get_language_model_service),
):
    return success_json(svc.get_language_models())


@router.get("/{provider_name}/icon")
def get_language_model_icon(
    provider_name: str,
    svc: LanguageModelService = Depends(get_language_model_service),
) -> StreamingResponse:
    icon, mimetype = svc.get_language_model_icon(provider_name)
    return StreamingResponse(io.BytesIO(icon), media_type=mimetype)


@router.get("/{provider_name}/{model_name}", response_model=LanguageModelResponse)
def get_language_model(
    provider_name: str,
    model_name: str,
    _: Account = Depends(get_current_account),
    svc: LanguageModelService = Depends(get_language_model_service),
):
    return success_json(svc.get_language_model(provider_name, model_name))
