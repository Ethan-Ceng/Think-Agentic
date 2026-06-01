import io

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import get_builtin_tool_service, get_current_account
from app.models.account import Account
from app.services.builtin_tool_service import BuiltinToolService
from app.shared.response import success_json

router = APIRouter(prefix="/builtin-tools", tags=["builtin_tool"])


@router.get("")
def get_builtin_tools(
    _: Account = Depends(get_current_account),
    svc: BuiltinToolService = Depends(get_builtin_tool_service),
):
    return success_json(svc.get_builtin_tools())


@router.get("/categories")
def get_categories(
    _: Account = Depends(get_current_account),
    svc: BuiltinToolService = Depends(get_builtin_tool_service),
):
    return success_json(svc.get_categories())


@router.get("/{provider_name}/tools/{tool_name}")
def get_provider_tool(
    provider_name: str,
    tool_name: str,
    _: Account = Depends(get_current_account),
    svc: BuiltinToolService = Depends(get_builtin_tool_service),
):
    return success_json(svc.get_provider_tool(provider_name, tool_name))


@router.get("/{provider_name}/icon")
def get_provider_icon(
    provider_name: str,
    svc: BuiltinToolService = Depends(get_builtin_tool_service),
) -> StreamingResponse:
    icon, mimetype = svc.get_provider_icon(provider_name)
    return StreamingResponse(io.BytesIO(icon), media_type=mimetype)

