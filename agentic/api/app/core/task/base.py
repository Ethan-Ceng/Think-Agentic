#!/usr/bin/env python
# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Optional, Protocol

from app.core.message_queue.base import MessageQueue


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

    def cancel(self) -> bool:
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
