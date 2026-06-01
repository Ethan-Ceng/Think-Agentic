from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_api_tool_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.api_tool import (
    ApiToolProviderPageItem,
    ApiToolProviderResponse,
    ApiToolResponse,
    CreateApiToolRequest,
    UpdateApiToolProviderRequest,
    ValidateOpenAPISchemaRequest,
)
from app.services.api_tool_service import ApiToolService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/api-tools", tags=["api_tool"])


@router.get("")
def get_api_tool_providers(
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    search_word: str = Query(default=""),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    providers, total_record, total_page = svc.get_api_tool_providers_with_page(
        session,
        current_user,
        search_word,
        current_page,
        page_size,
    )
    return success_json(
        {
            "list": [ApiToolProviderPageItem.from_provider(provider).model_dump() for provider in providers],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_api_tool_provider(
    req: CreateApiToolRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    svc.create_api_tool(
        session,
        req.name,
        str(req.icon),
        req.openapi_schema,
        [header.model_dump() for header in req.headers],
        current_user,
    )
    return success_message("Create API tool provider success")


@router.post("/validate")
def validate_openapi_schema(
    req: ValidateOpenAPISchemaRequest,
    _: Account = Depends(get_current_account),
):
    ApiToolService.parse_openapi_schema(req.openapi_schema)
    return success_message("Validate OpenAPI schema success")


@router.get("/{provider_id}")
def get_api_tool_provider(
    provider_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    provider = svc.get_api_tool_provider(session, provider_id, current_user)
    return success_json(ApiToolProviderResponse.from_provider(provider).model_dump())


@router.put("/{provider_id}")
def update_api_tool_provider(
    provider_id: UUID,
    req: UpdateApiToolProviderRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    svc.update_api_tool_provider(
        session,
        provider_id,
        req.name,
        str(req.icon),
        req.openapi_schema,
        [header.model_dump() for header in req.headers],
        current_user,
    )
    return success_message("Update API tool provider success")


@router.delete("/{provider_id}")
def delete_api_tool_provider(
    provider_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    svc.delete_api_tool_provider(session, provider_id, current_user)
    return success_message("Delete API tool provider success")


@router.get("/{provider_id}/tools/{tool_name}")
def get_api_tool(
    provider_id: UUID,
    tool_name: str,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ApiToolService = Depends(get_api_tool_service),
):
    tool = svc.get_api_tool(session, provider_id, tool_name, current_user)
    return success_json(ApiToolResponse.from_tool(tool).model_dump())

