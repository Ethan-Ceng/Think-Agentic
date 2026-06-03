from collections.abc import Generator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.tools.builtin_tools.categories import BuiltinCategoryManager
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.infrastructure.db import get_session
from app.models.account import Account
from app.services.account_service import AccountService
from app.services.agent_task_service import AgentTaskService
from app.services.ai_service import AIService
from app.services.analysis_service import AnalysisService
from app.services.api_key_service import ApiKeyService
from app.services.api_tool_service import ApiToolService
from app.services.app_service import AppService
from app.services.assistant_agent_service import AssistantAgentService
from app.services.audio_service import AudioService
from app.services.builtin_app_service import BuiltinAppService
from app.services.builtin_tool_service import BuiltinToolService
from app.services.conversation_service import ConversationService
from app.services.dataset_service import DatasetService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.jwt_service import JwtService
from app.services.language_model_service import LanguageModelService
from app.services.llm_provider_service import LLMProviderService
from app.services.oauth_service import OAuthService
from app.services.openapi_service import OpenAPIService
from app.services.platform_service import PlatformService
from app.services.router_agent_manager_service import RouterAgentManagerService
from app.services.segment_service import SegmentService
from app.services.setting_service import SettingService
from app.services.upload_file_service import UploadFileService
from app.services.web_app_service import WebAppService
from app.services.wechat_service import WechatService
from app.services.workflow_service import WorkflowService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_session() -> Generator[Session, None, None]:
    yield from get_session()


def get_jwt_service(settings: Settings = Depends(get_settings)) -> JwtService:
    return JwtService(settings=settings)


def get_account_service(jwt_service: JwtService = Depends(get_jwt_service)) -> AccountService:
    return AccountService(jwt_service=jwt_service)


def get_api_key_service() -> ApiKeyService:
    return ApiKeyService()


def get_analysis_service() -> AnalysisService:
    return AnalysisService()


def get_ai_service() -> AIService:
    return AIService()


def get_api_tool_service() -> ApiToolService:
    return ApiToolService()


def get_app_service() -> AppService:
    return AppService()


def get_agent_task_service() -> AgentTaskService:
    return AgentTaskService()


def get_router_agent_manager_service() -> RouterAgentManagerService:
    return RouterAgentManagerService()


def get_assistant_agent_service(settings: Settings = Depends(get_settings)) -> AssistantAgentService:
    return AssistantAgentService(settings=settings)


def get_audio_service(settings: Settings = Depends(get_settings)) -> AudioService:
    return AudioService(settings=settings)


def get_conversation_service() -> ConversationService:
    return ConversationService()


def get_dataset_service() -> DatasetService:
    return DatasetService()


def get_document_service() -> DocumentService:
    return DocumentService()


def get_file_service() -> FileService:
    return FileService()


def get_segment_service() -> SegmentService:
    return SegmentService()


def get_setting_service() -> SettingService:
    return SettingService()


def get_upload_file_service() -> UploadFileService:
    return UploadFileService()


def get_builtin_tool_service() -> BuiltinToolService:
    return BuiltinToolService(
        builtin_provider_manager=BuiltinProviderManager(),
        builtin_category_manager=BuiltinCategoryManager(),
    )


def get_builtin_app_service() -> BuiltinAppService:
    return BuiltinAppService()


def get_language_model_service(settings: Settings = Depends(get_settings)) -> LanguageModelService:
    return LanguageModelService(settings=settings)


def get_llm_provider_service() -> LLMProviderService:
    return LLMProviderService()


def get_openapi_service() -> OpenAPIService:
    return OpenAPIService()


def get_web_app_service() -> WebAppService:
    return WebAppService()


def get_platform_service() -> PlatformService:
    return PlatformService()


def get_wechat_service() -> WechatService:
    return WechatService()


def get_workflow_service() -> WorkflowService:
    return WorkflowService(builtin_provider_manager=BuiltinProviderManager())


def get_oauth_service(
    settings: Settings = Depends(get_settings),
    jwt_service: JwtService = Depends(get_jwt_service),
    account_service: AccountService = Depends(get_account_service),
) -> OAuthService:
    return OAuthService(settings=settings, jwt_service=jwt_service, account_service=account_service)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("unauthorized", "Missing or invalid Authorization header", status_code=401)
    return authorization[7:]


def get_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    if not x_api_key:
        raise AppError("unauthorized", "Missing X-API-Key header", status_code=401)
    return x_api_key


def get_current_account(
    token: str = Depends(get_bearer_token),
    session: Session = Depends(get_db_session),
    account_service: AccountService = Depends(get_account_service),
) -> Account:
    account = account_service.get_account_by_token(session, token)
    if account is None:
        raise AppError("unauthorized", "Invalid or expired token", status_code=401)
    return account


def get_api_key_account(
    x_api_key: str = Depends(get_api_key),
    session: Session = Depends(get_db_session),
    api_key_service: ApiKeyService = Depends(get_api_key_service),
) -> Account:
    api_key = api_key_service.get_api_key_by_credential(session, x_api_key)
    if api_key is None or not api_key.is_active:
        raise AppError("unauthorized", "Invalid or inactive API key", status_code=401)
    account = session.get(Account, api_key.account_id)
    if account is None:
        raise AppError("unauthorized", "API key account does not exist", status_code=401)
    return account
