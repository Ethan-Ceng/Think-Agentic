#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stable, user-safe failure contracts shared by events, tools, and traces."""
from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class FailureCategory(str, Enum):
    MODEL = "model"
    PROVIDER = "provider"
    TOOL = "tool"
    RUNTIME = "runtime"
    INTERACTION = "interaction"
    CONFIG = "config"


class FailureScope(str, Enum):
    OPERATION = "operation"
    STEP = "step"
    RUN = "run"


class RecoveryAction(str, Enum):
    RETRY = "retry"
    CONTINUE = "continue"
    CHOOSE_PROVIDER = "choose_provider"
    CHECK_CONFIG = "check_config"
    REAUTHORIZE = "reauthorize"
    START_NEW_RUN = "start_new_run"


class RunFailureCode(str, Enum):
    CANCELLED_BY_USER = "RUN_CANCELLED_BY_USER"
    CANCELLED_BY_SHUTDOWN = "RUN_CANCELLED_BY_SHUTDOWN"
    CONTEXT_LOST = "RUN_CONTEXT_LOST"
    ITERATION_LIMIT = "RUN_ITERATION_LIMIT"
    INTERNAL_ERROR = "RUN_INTERNAL_ERROR"


class FailureInfo(BaseModel):
    """Safe failure projection; internal exceptions never belong in this model."""

    code: str = Field(min_length=3, max_length=64, pattern=r"^[A-Z0-9_]+$")
    category: FailureCategory
    scope: FailureScope
    source: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_.-]+$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    recovery_actions: list[RecoveryAction] = Field(default_factory=list)
    provider_id: str | None = Field(default=None, max_length=160)
    tool_call_id: str | None = Field(default=None, max_length=160)
    debug_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        min_length=1,
        max_length=64,
    )

    @field_validator("recovery_actions")
    @classmethod
    def _deduplicate_actions(
        cls,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        return list(dict.fromkeys(actions))


def run_failure(code: RunFailureCode) -> FailureInfo:
    definitions: dict[
        RunFailureCode,
        tuple[str, bool, list[RecoveryAction]],
    ] = {
        RunFailureCode.CANCELLED_BY_USER: (
            "已停止本次执行。",
            False,
            [RecoveryAction.START_NEW_RUN],
        ),
        RunFailureCode.CANCELLED_BY_SHUTDOWN: (
            "服务关闭时中断了本次执行。",
            True,
            [RecoveryAction.CONTINUE, RecoveryAction.START_NEW_RUN],
        ),
        RunFailureCode.CONTEXT_LOST: (
            "本次运行上下文已丢失；当前进程无法继续，你可以基于已有结果继续。",
            True,
            [RecoveryAction.CONTINUE, RecoveryAction.START_NEW_RUN],
        ),
        RunFailureCode.ITERATION_LIMIT: (
            "任务达到最大执行轮次，当前结果未能完成。",
            True,
            [RecoveryAction.CONTINUE, RecoveryAction.START_NEW_RUN],
        ),
        RunFailureCode.INTERNAL_ERROR: (
            "本次回复未完成，请稍后重试。",
            True,
            [RecoveryAction.RETRY, RecoveryAction.START_NEW_RUN],
        ),
    }
    message, retryable, actions = definitions[code]
    return FailureInfo(
        code=code.value,
        category=FailureCategory.RUNTIME,
        scope=FailureScope.RUN,
        source="runtime",
        message=message,
        retryable=retryable,
        recovery_actions=actions,
    )
