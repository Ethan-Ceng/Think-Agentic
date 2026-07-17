#!/usr/bin/env python
# -*- coding: utf-8 -*-
from functools import lru_cache

from app.core.config import get_settings
from app.core.json_parser.repair_json_parser import RepairJSONParser
from app.core.llm.openai_llm import OpenAILLM
from app.core.sandbox.docker_sandbox import DockerSandbox
from app.core.search.bing_search import BingSearchEngine
from app.core.skills.limits import SkillPackageLimits
from app.core.skills.package import SkillPackageService
from app.core.task.redis_stream_task import RedisStreamTask
from app.extensions.managed_file_storage import ManagedFileStorage
from app.extensions.skill_package_storage import SkillPackageStorage
from app.repositories.file_app_config_repository import FileAppConfigRepository
from app.services.skill_workspace_service import SkillWorkspaceService
from app.services.bundled_skill_service import BundledSkillService
from app.services.user_config_service import UserConfigService

settings = get_settings()


def get_file_storage() -> ManagedFileStorage:
    from app.dependencies.uow import get_uow

    return ManagedFileStorage(uow_factory=get_uow)


def get_skill_package_service() -> SkillPackageService:
    return SkillPackageService(
        SkillPackageLimits(
            archive_bytes=settings.skill_package_archive_max_bytes,
            extracted_bytes=settings.skill_package_extracted_max_bytes,
            file_count=settings.skill_package_file_count_max,
            file_bytes=settings.skill_package_file_max_bytes,
            skill_md_bytes=settings.skill_package_manifest_max_bytes,
            relative_path_chars=settings.skill_package_relative_path_max_chars,
        )
    )


def get_skill_package_storage() -> SkillPackageStorage:
    from app.dependencies.uow import get_uow

    return SkillPackageStorage(UserConfigService(get_uow), settings=settings)


def get_skill_workspace_service() -> SkillWorkspaceService:
    return SkillWorkspaceService(
        root=settings.skill_workspace_storage_path,
        package_service=get_skill_package_service(),
        max_text_file_bytes=settings.skill_package_file_max_bytes,
    )


@lru_cache
def get_bundled_skill_service() -> BundledSkillService:
    return BundledSkillService(package_service=get_skill_package_service())


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
