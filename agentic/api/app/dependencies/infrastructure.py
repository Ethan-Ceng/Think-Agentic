#!/usr/bin/env python
# -*- coding: utf-8 -*-
from app.core.config import get_settings
from app.core.json_parser.repair_json_parser import RepairJSONParser
from app.core.llm.openai_llm import OpenAILLM
from app.core.sandbox.docker_sandbox import DockerSandbox
from app.core.search.bing_search import BingSearchEngine
from app.core.task.redis_stream_task import RedisStreamTask
from app.extensions.cos_file_storage import CosFileStorage
from app.extensions.storage import Storage
from app.repositories.file_app_config_repository import FileAppConfigRepository

settings = get_settings()


def get_file_storage(storage: Storage) -> CosFileStorage:
    from app.dependencies.uow import get_uow

    return CosFileStorage(
        bucket=settings.cos_bucket,
        cos=storage,
        uow_factory=get_uow,
    )


def get_app_config():
    return FileAppConfigRepository(config_path=settings.app_config_filepath).load()


def get_llm(llm_config):
    return OpenAILLM(llm_config)


def get_json_parser():
    return RepairJSONParser()


def get_search_engine():
    return BingSearchEngine()


sandbox_cls = DockerSandbox
task_cls = RedisStreamTask
