#!/usr/bin/env python
# -*- coding: utf-8 -*-
from functools import lru_cache

from app.dependencies.infrastructure import (
    get_a2a_provider_runtime,
    get_bundled_skill_service,
    get_file_storage,
    get_diagnostic_llm,
    get_json_parser,
    get_llm,
    get_mcp_provider_pool,
    get_search_engine,
    get_skill_package_service,
    get_skill_package_storage,
    get_skill_workspace_service,
    sandbox_cls,
    task_cls,
)
from app.dependencies.uow import get_uow
from app.schemas.provider_diagnostic import ProviderType
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.marketplace_skill_service import MarketplaceSkillService
from app.services.session_service import SessionService
from app.services.trace_service import TraceService
from app.services.search_service import SearchService
from app.services.skill_service import SkillService
from app.services.user_config_service import UserConfigService
from app.services.project_service import ProjectService
from app.services.provider_diagnostic_service import (
    A2AProviderDiagnosticAdapter,
    APIProviderDiagnosticAdapter,
    LLMProviderDiagnosticAdapter,
    MCPProviderDiagnosticAdapter,
    ProviderDiagnosticService,
)
from app.services.tool_config_service import ToolConfigService


def get_auth_service() -> AuthService:
    return AuthService(uow_factory=get_uow)


def get_user_config_service() -> UserConfigService:
    return UserConfigService(uow_factory=get_uow)


@lru_cache
def get_provider_diagnostic_service() -> ProviderDiagnosticService:
    user_config_service = get_user_config_service()
    return ProviderDiagnosticService(
        adapters={
            ProviderType.LLM: LLMProviderDiagnosticAdapter(
                user_config_service=user_config_service,
                llm_factory=get_diagnostic_llm,
            ),
            ProviderType.MCP: MCPProviderDiagnosticAdapter(
                user_config_service=user_config_service,
                provider_pool=get_mcp_provider_pool(),
            ),
            ProviderType.A2A: A2AProviderDiagnosticAdapter(
                user_config_service=user_config_service,
                provider_runtime=get_a2a_provider_runtime(),
            ),
            ProviderType.API: APIProviderDiagnosticAdapter(
                tool_config_service=ToolConfigService(user_config_service),
            ),
        }
    )


def get_session_service() -> SessionService:
    return SessionService(uow_factory=get_uow, sandbox_cls=sandbox_cls)


def get_trace_service() -> TraceService:
    return TraceService(uow_factory=get_uow)


def get_search_service() -> SearchService:
    return SearchService(uow_factory=get_uow)


def get_project_service() -> ProjectService:
    return ProjectService(uow_factory=get_uow)


def get_file_service() -> FileService:
    return FileService(
        uow_factory=get_uow,
        file_storage=get_file_storage(),
    )


def get_skill_service() -> SkillService:
    return SkillService(
        uow_factory=get_uow,
        package_service=get_skill_package_service(),
        package_storage=get_skill_package_storage(),
        workspace_service=get_skill_workspace_service(),
    )


def get_marketplace_skill_service() -> MarketplaceSkillService:
    return MarketplaceSkillService(
        uow_factory=get_uow,
        package_service=get_skill_package_service(),
        package_storage=get_skill_package_storage(),
        personal_skill_service=get_skill_service(),
    )


def get_agent_service() -> AgentService:
    return AgentService(
        uow_factory=get_uow,
        user_config_service=get_user_config_service(),
        llm_factory=get_llm,
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=get_json_parser(),
        search_engine=get_search_engine(),
        file_storage=get_file_storage(),
        skill_package_storage=get_skill_package_storage(),
        bundled_skill_service=get_bundled_skill_service(),
        skill_workspace_service=get_skill_workspace_service(),
        a2a_provider_runtime=get_a2a_provider_runtime(),
        mcp_provider_pool=get_mcp_provider_pool(),
    )
