#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/14 10:48
@Author  : thezehui@gmail.com
@File    : session_repository.py
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, List, Optional

from app.core.entities.event import BaseEvent, InteractionDecision, InteractionEvent
from app.core.entities.file import File
from app.core.entities.memory import Memory
from app.core.entities.session import (
    BranchContextMessage,
    BranchOperation,
    NextMessage,
    Session,
    SessionStatus,
)


@dataclass(frozen=True)
class SessionBranchFamily:
    """Owned direct branch family resolved around one source message."""

    source_session: Optional[Session]
    target_event_id: str
    current_session: Session
    variants: tuple[Session, ...]


class SessionRepository(Protocol):
    """会话仓库协议定义"""

    async def save(self, session: Session) -> None:
        """存储或更新传递进来的会话"""
        ...

    async def get_all(self) -> List[Session]:
        """获取所有会话列表信息"""
        ...

    async def get_all_by_user(
            self, user_id: str, archived: bool = False
    ) -> List[Session]:
        """获取指定用户的会话列表信息"""
        ...

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """根据传递的会话id查询会话"""
        ...

    async def get_by_id_for_user(self, session_id: str, user_id: str) -> Optional[Session]:
        """根据会话id和用户id查询会话"""
        ...

    async def delete_by_id(self, session_id: str) -> None:
        """根据传递的会话id删除会话"""
        ...

    async def delete_by_id_for_user(self, session_id: str, user_id: str) -> None:
        """根据传递的会话id和用户id删除会话"""
        ...

    async def update_title(self, session_id: str, title: str) -> None:
        """兼容旧调用；按自动标题规则更新会话信息"""
        ...

    async def update_generated_title(self, session_id: str, title: str) -> bool:
        """仅在标题未被用户锁定时更新，返回是否写入"""
        ...

    async def update_manual_title(
            self, session_id: str, user_id: str, title: str
    ) -> Session:
        """更新所属会话标题并锁定后续自动标题"""
        ...

    async def update_organization(
            self,
            session_id: str,
            user_id: str,
            *,
            title: Optional[str] = None,
            pinned: Optional[bool] = None,
            archived: Optional[bool] = None,
            project_id: Optional[str] = None,
            project_id_provided: bool = False,
    ) -> Session:
        """原子更新所属会话的导航整理元数据"""
        ...

    async def claim_execution(
            self,
            session_id: str,
            user_id: str,
    ) -> tuple[Session, Optional[SessionStatus]]:
        """原子确认会话未归档，并在新 Run 时占用运行态。"""
        ...

    async def update_runtime_handles(
            self,
            session_id: str,
            *,
            sandbox_id: Optional[str] = None,
            task_id: Optional[str] = None,
    ) -> None:
        """只更新 Agent 运行句柄，避免覆盖并发写入的导航元数据。"""
        ...

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        """根据传递的信息更新最新消息"""
        ...

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        """根据传递的信息更新未读消息数"""
        ...

    async def increment_unread_message_count(self, session_id: str) -> None:
        """根据传递的会话id新增未读消息数"""
        ...

    async def decrement_unread_message_count(self, session_id: str) -> None:
        """根据传递的会话id减少未读消息数"""
        ...

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        """根据传递的会话id更新会话状态"""
        ...

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        """往会话中新增事件"""
        ...

    async def create_branch(
            self,
            source_session_id: str,
            user_id: str,
            target_event_id: str,
            operation: BranchOperation,
            request_id: str,
            message: Optional[str] = None,
    ) -> Session:
        """Atomically create or replay an immutable conversation branch."""
        ...

    async def get_branch_family(
            self,
            session_id: str,
            user_id: str,
            target_event_id: Optional[str] = None,
    ) -> SessionBranchFamily:
        """Resolve one owned source and its same-anchor direct child branches."""
        ...

    async def put_next_message(
            self, session_id: str, user_id: str, next_message: NextMessage
    ) -> NextMessage:
        """Create or replace the queued next message for an owned running session."""
        ...

    async def cancel_next_message(self, session_id: str, user_id: str) -> None:
        """Cancel an owned queued message; cancellation is idempotent."""
        ...

    async def finish_or_claim_next_message(
            self, session_id: str, task_id: str
    ) -> Optional[NextMessage]:
        """Atomically claim queued work or mark the session completed."""
        ...

    async def start_next_message_run(self, session_id: str, user_id: str) -> Session:
        """Atomically reopen a completed owned session that still has queued work."""
        ...

    async def consume_next_message(
            self,
            session_id: str,
            message_id: str,
            task_id: str,
            event: BaseEvent,
    ) -> None:
        """Persist the accepted user event and clear its processing slot."""
        ...

    async def reset_processing_next_message(self, session_id: str) -> Optional[NextMessage]:
        """Return an orphaned processing slot to queued state."""
        ...

    async def resolve_interaction(
            self,
            session_id: str,
            user_id: str,
            action_id: str,
            decision: InteractionDecision,
            answer: Optional[str] = None,
            selected_values: Optional[List[str]] = None,
    ) -> InteractionEvent:
        """Atomically resolve the current pending interaction for a session owner."""
        ...

    async def add_file(self, session_id: str, file: File) -> None:
        """往会话中新增文件"""
        ...

    async def remove_file(self, session_id: str, file_id: str) -> None:
        """根据传递的会话id+文件id移除文件"""
        ...

    async def get_file_by_path(self, session_id: str, filepath: str) -> Optional[File]:
        """查询会话中的文件信息"""
        ...

    async def save_memory(self, session_id: str, agent_name: str, memory: Memory) -> None:
        """更新or创建会话中指定Agent的记忆"""
        ...

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        """根据传递的会话id+Agent名字获取记忆"""
        ...

    async def get_branch_context_seed(
            self, session_id: str
    ) -> List[BranchContextMessage]:
        """Read the server-validated visible transcript seed for an Agent."""
        ...
