#!/usr/bin/env python
# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Protocol

from app.core.message_queue.base import MessageQueue


class RunCancellationReason(str, Enum):
    USER = "user"
    SHUTDOWN = "shutdown"
    TIMEOUT = "timeout"
    CLIENT_DISCONNECT = "client_disconnect"


@dataclass(frozen=True, slots=True)
class RunCancellationContext:
    reason: RunCancellationReason
    requested_by: str
    requested_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TaskRunner(ABC):
    """Runs a task and owns its runtime resources."""

    @abstractmethod
    async def invoke(self, task: "Task") -> None:
        raise NotImplementedError

    @abstractmethod
    async def destroy(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def on_done(self, task: "Task") -> None:
        raise NotImplementedError


class Task(Protocol):
    """Task instance protocol."""

    async def invoke(self) -> None:
        ...

    def cancel(
        self,
        *,
        reason: RunCancellationReason = RunCancellationReason.USER,
        requested_by: str = "user",
    ) -> bool:
        ...

    @property
    def cancellation_context(self) -> RunCancellationContext | None:
        ...

    @property
    def input_stream(self) -> MessageQueue:
        ...

    @property
    def output_stream(self) -> MessageQueue:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def done(self) -> bool:
        ...

    @classmethod
    def get(cls, task_id: str) -> Optional["Task"]:
        ...

    @classmethod
    def create(cls, task_runner: TaskRunner) -> "Task":
        ...

    @classmethod
    async def destroy(cls) -> None:
        ...
