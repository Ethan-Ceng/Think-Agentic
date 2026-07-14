#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fastapi import Depends

from app.dependencies.infrastructure import (
    get_file_storage,
    get_json_parser,
    get_llm,
    get_search_engine,
    sandbox_cls,
    task_cls,
)
from app.dependencies.uow import get_uow
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.session_service import SessionService
from app.services.trace_service import TraceService
from app.services.user_config_service import UserConfigService


def get_auth_service() -> AuthService:
    return AuthService(uow_factory=get_uow)


def get_user_config_service() -> UserConfigService:
    return UserConfigService(uow_factory=get_uow)


def get_session_service() -> SessionService:
    return SessionService(uow_factory=get_uow, sandbox_cls=sandbox_cls)


def get_trace_service() -> TraceService:
    return TraceService(uow_factory=get_uow)


def get_file_service() -> FileService:
    return FileService(
        uow_factory=get_uow,
        file_storage=get_file_storage(),
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
    )
