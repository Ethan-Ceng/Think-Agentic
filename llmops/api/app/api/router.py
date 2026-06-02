from fastapi import FastAPI

from app.api.routers.account import router as account_router
from app.api.routers.ai import router as ai_router
from app.api.routers.analysis import router as analysis_router
from app.api.routers.api_key import router as api_key_router
from app.api.routers.api_tool import router as api_tool_router
from app.api.routers.app import router as app_router
from app.api.routers.assistant_agent import router as assistant_agent_router
from app.api.routers.audio import router as audio_router
from app.api.routers.auth import router as auth_router
from app.api.routers.builtin_app import router as builtin_app_router
from app.api.routers.builtin_tool import router as builtin_tool_router
from app.api.routers.conversation import router as conversation_router
from app.api.routers.dataset import router as dataset_router
from app.api.routers.document import router as document_router
from app.api.routers.files import router as files_router
from app.api.routers.inner import router as inner_router
from app.api.routers.language_model import router as language_model_router
from app.api.routers.llm_provider import router as llm_provider_router
from app.api.routers.oauth import router as oauth_router
from app.api.routers.openapi import router as openapi_router
from app.api.routers.platform import router as platform_router
from app.api.routers.segment import router as segment_router
from app.api.routers.service_api import router as service_api_router
from app.api.routers.setting import router as setting_router
from app.api.routers.system import router as system_router
from app.api.routers.triggers import router as triggers_router
from app.api.routers.upload_file import router as upload_file_router
from app.api.routers.web import router as web_router
from app.api.routers.web_app import router as web_app_router
from app.api.routers.wechat import router as wechat_router
from app.api.routers.workflow import router as workflow_router


def register_routers(app: FastAPI) -> None:
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(analysis_router)
    app.include_router(ai_router)
    app.include_router(api_key_router)
    app.include_router(app_router)
    app.include_router(assistant_agent_router)
    app.include_router(audio_router)
    app.include_router(api_tool_router)
    app.include_router(builtin_app_router)
    app.include_router(builtin_tool_router)
    app.include_router(language_model_router)
    app.include_router(llm_provider_router)
    app.include_router(conversation_router)
    app.include_router(dataset_router)
    app.include_router(document_router)
    app.include_router(segment_router)
    app.include_router(setting_router)
    app.include_router(upload_file_router)
    app.include_router(workflow_router)
    app.include_router(oauth_router)
    app.include_router(openapi_router)
    app.include_router(web_app_router)
    app.include_router(platform_router)
    app.include_router(wechat_router)
    app.include_router(service_api_router)
    app.include_router(web_router)
    app.include_router(files_router)
    app.include_router(inner_router)
    app.include_router(triggers_router)
