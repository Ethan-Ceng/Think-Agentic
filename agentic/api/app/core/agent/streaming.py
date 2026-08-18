from __future__ import annotations

import uuid

from app.core.agent.base import ProjectedMessageDelta
from app.core.entities.event import MessageDeltaEvent


class VisibleMessageStream:
    """把 Agent 内部投影增量关联为一个稳定的公共草稿流。"""

    def __init__(self) -> None:
        self._stream_id = str(uuid.uuid4())
        self._sequence = 0
        self._active = False

    @property
    def final_stream_id(self) -> str | None:
        return self._stream_id if self._active else None

    def map(self, event: ProjectedMessageDelta) -> MessageDeltaEvent:
        mapped = MessageDeltaEvent(
            stream_id=self._stream_id,
            sequence=self._sequence,
            delta=event.delta,
            operation=event.operation,
        )
        self._sequence += 1
        if event.operation == "append":
            self._active = True
        elif event.operation == "abort":
            self._active = False
        return mapped

    def abort(self) -> MessageDeltaEvent | None:
        if not self._active:
            return None
        return self.map(ProjectedMessageDelta(delta="", operation="abort"))

