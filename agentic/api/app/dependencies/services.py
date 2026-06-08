#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fastapi import Depends

from app.dependencies.infrastructure import (
    get_app_config,
    get_file_storage,
    get_json_parser,
    get_llm,
    get_search_engine,
    sandbox_cls,
    task_cls,
)
from app.dependencies.uow import get_uow
from app.extensions.storage import Storage, get_storage
from app.services.agent_service import AgentService
from app.services.file_service import FileService
from app.services.session_service import SessionService


def get_session_service() -> SessionService:
    return SessionService(uow_factory=get_uow, sandbox_cls=sandbox_cls)


def get_file_service(
    storage: Storage = Depends(get_storage),
) -> FileService:
    return FileService(
        uow_factory=get_uow,
        file_storage=get_file_storage(storage),
    )


def get_agent_service(
    storage: Storage = Depends(get_storage),
) -> AgentService:
    app_config = get_app_config()
    return AgentService(
        uow_factory=get_uow,
        llm=get_llm(app_config.llm_config),
        agent_config=app_config.agent_config,
        mcp_config=app_config.mcp_config,
        a2a_config=app_config.a2a_config,
        tool_config=app_config.tool_config,
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=get_json_parser(),
        search_engine=get_search_engine(),
        file_storage=get_file_storage(storage),
    )
