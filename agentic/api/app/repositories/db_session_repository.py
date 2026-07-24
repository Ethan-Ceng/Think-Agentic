#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/14 9:28
@Author  : thezehui@gmail.com
@File    : db_session_repository.py
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, delete, update, func, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.event import (
    BaseEvent,
    InteractionDecision,
    InteractionEvent,
    MessageEvent,
)
from app.core.entities.file import File
from app.core.entities.memory import Memory
from app.core.entities.session import (
    BranchContextMessage,
    BranchOperation,
    InteractionNotFoundError,
    NextMessage,
    NextMessageConflictError,
    NextMessageNotFoundError,
    NextMessageState,
    Session,
    SessionBranchConflictError,
    SessionBranchNotFoundError,
    SessionStatus,
)
from app.repositories.session_repository import SessionRepository
from app.models import FileModel, SessionModel


class DBSessionRepository(SessionRepository):
    """基于Postgres数据库的会话仓库"""

    def __init__(self, db_session: AsyncSession) -> None:
        """构造函数，完成数据仓库的初始化"""
        self.db_session = db_session

    async def _get_session_record_for_update(
            self, session_id: str, user_id: Optional[str] = None
    ) -> SessionModel:
        conditions = [SessionModel.id == session_id]
        if user_id is not None:
            conditions.append(SessionModel.user_id == user_id)
        result = await self.db_session.execute(
            select(SessionModel).where(*conditions).with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NextMessageNotFoundError("会话不存在或无权访问")
        return record

    async def save(self, session: Session) -> None:
        """根据传递的领域模型更新或者新增会话"""
        # 1.根据id查询会话是否存在
        stmt = select(SessionModel).where(SessionModel.id == session.id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        # 2.如果会话不存在则新建会话
        if not record:
            record = SessionModel.from_domain(session)
            self.db_session.add(record)
            return

        # 3.会话存在则更新会话
        record.update_from_domain(session)

    async def create_branch(
            self,
            source_session_id: str,
            user_id: str,
            target_event_id: str,
            operation: BranchOperation,
            request_id: str,
            message: Optional[str] = None,
    ) -> Session:
        """Create an immutable session snapshot while the owned source row is locked."""
        source_result = await self.db_session.execute(
            select(SessionModel)
            .where(
                SessionModel.id == source_session_id,
                SessionModel.user_id == user_id,
            )
            .with_for_update()
        )
        source = source_result.scalar_one_or_none()
        if source is None:
            raise SessionBranchNotFoundError("会话不存在或无权访问")

        existing_result = await self.db_session.execute(
            select(SessionModel).where(
                SessionModel.branch_request_id == request_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return self._validate_branch_replay(
                existing=existing,
                user_id=user_id,
                source_session_id=source_session_id,
                target_event_id=target_event_id,
                operation=operation,
            )

        if (
            source.status != SessionStatus.COMPLETED.value
            or source.next_message is not None
        ):
            raise SessionBranchConflictError("仅可从已完成且没有排队消息的会话创建分支")

        visible_messages = [
            MessageEvent.model_validate(raw_event)
            for raw_event in (source.events or [])
            if raw_event.get("type") == "message"
            and raw_event.get("visible", True)
        ]
        target_index = next(
            (
                index
                for index, event in enumerate(visible_messages)
                if event.id == target_event_id
            ),
            None,
        )
        if target_index is None:
            raise SessionBranchNotFoundError("目标消息不存在或不可见")

        replay: Optional[MessageEvent] = None
        if operation == BranchOperation.FORK:
            prefix = visible_messages[: target_index + 1]
        elif operation == BranchOperation.EDIT:
            target = visible_messages[target_index]
            if target.role != "user":
                raise SessionBranchConflictError("只能编辑用户消息")
            revised = (message or "").strip()
            if not revised:
                raise SessionBranchConflictError("编辑后的消息不能为空")
            prefix = visible_messages[:target_index]
            replay = target.model_copy(update={"message": revised})
        elif operation == BranchOperation.REGENERATE:
            target = visible_messages[target_index]
            if target.role != "assistant":
                raise SessionBranchConflictError("只能重新生成助手消息")
            replay_index = next(
                (
                    index
                    for index in range(target_index - 1, -1, -1)
                    if visible_messages[index].role == "user"
                ),
                None,
            )
            if replay_index is None:
                raise SessionBranchConflictError("助手消息之前没有可重放的用户消息")
            prefix = visible_messages[:replay_index]
            replay = visible_messages[replay_index]
        else:
            raise SessionBranchConflictError("不支持的分支操作")

        attachment_ids: List[str] = []
        for event in [*prefix, *([replay] if replay is not None else [])]:
            for attachment in event.attachments:
                if attachment.id not in attachment_ids:
                    attachment_ids.append(attachment.id)

        accessible_files = {}
        if attachment_ids:
            files_result = await self.db_session.execute(
                select(FileModel).where(
                    FileModel.id.in_(attachment_ids),
                    FileModel.user_id == user_id,
                    FileModel.status == "available",
                )
            )
            accessible_files = {
                record.id: record.to_domain()
                for record in files_result.scalars().all()
            }
            if set(accessible_files) != set(attachment_ids):
                raise SessionBranchConflictError("分支引用的附件已不可访问")

        copied_events = []
        for event in prefix:
            copied_events.append(
                MessageEvent(
                    role=event.role,
                    message=event.message,
                    attachments=[
                        accessible_files[attachment.id]
                        for attachment in event.attachments
                    ],
                    skills=event.skills,
                    visible=True,
                    created_at=event.created_at,
                )
            )

        next_message = None
        if replay is not None:
            next_message = NextMessage(
                message=replay.message,
                attachment_ids=[attachment.id for attachment in replay.attachments],
                skills=replay.skills,
            )

        context_seed = [
            BranchContextMessage(
                role=event.role,
                content=event.message,
                attachment_names=[
                    attachment.filename for attachment in event.attachments
                ],
            )
            for event in copied_events
        ]
        branch_files = [
            accessible_files[file_id]
            for file_id in attachment_ids
        ]
        latest_event = copied_events[-1] if copied_events else None
        latest_message = (
            replay.message
            if replay is not None
            else latest_event.message if latest_event is not None else ""
        )
        latest_message_at = (
            datetime.now()
            if replay is not None
            else latest_event.created_at if latest_event is not None else None
        )
        title_suffix = " · 分支"
        branch = Session(
            user_id=user_id,
            title=f"{source.title[: 255 - len(title_suffix)]}{title_suffix}",
            latest_message=latest_message,
            latest_message_at=latest_message_at,
            events=copied_events,
            files=branch_files,
            next_message=next_message,
            source_session_id=source_session_id,
            forked_from_event_id=target_event_id,
            branch_operation=operation,
            branch_request_id=request_id,
            context_seed=context_seed,
            status=SessionStatus.COMPLETED,
        )
        try:
            async with self.db_session.begin_nested():
                self.db_session.add(SessionModel.from_domain(branch))
                await self.db_session.flush()
        except IntegrityError:
            winner_result = await self.db_session.execute(
                select(SessionModel).where(
                    SessionModel.branch_request_id == request_id,
                )
            )
            winner = winner_result.scalar_one_or_none()
            if winner is None:
                raise
            return self._validate_branch_replay(
                existing=winner,
                user_id=user_id,
                source_session_id=source_session_id,
                target_event_id=target_event_id,
                operation=operation,
            )
        return branch

    @staticmethod
    def _validate_branch_replay(
            *,
            existing: SessionModel,
            user_id: str,
            source_session_id: str,
            target_event_id: str,
            operation: BranchOperation,
    ) -> Session:
        if (
            existing.user_id != user_id
            or existing.source_session_id != source_session_id
            or existing.forked_from_event_id != target_event_id
            or existing.branch_operation != operation.value
        ):
            raise SessionBranchConflictError("request_id 已用于其他分支请求")
        return existing.to_domain()

    async def get_all(self) -> List[Session]:
        """获取所有会话列表"""
        # 1.构建sql查询所有记录
        stmt = select(SessionModel).order_by(SessionModel.latest_message_at.desc())
        result = await self.db_session.execute(stmt)
        records = result.scalars().all()

        # 2.将数据循环遍历成Session
        return [record.to_domain() for record in records]

    async def get_all_by_user(self, user_id: str) -> List[Session]:
        """获取指定用户的会话列表"""
        stmt = (
            select(SessionModel)
            .where(SessionModel.user_id == user_id)
            .order_by(SessionModel.latest_message_at.desc())
        )
        result = await self.db_session.execute(stmt)
        records = result.scalars().all()
        return [record.to_domain() for record in records]

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """根据id查询会话"""
        # 1.根据id查询会话是否存在
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        # 2.判断会话记录是否存在并返回
        return record.to_domain() if record is not None else None

    async def get_by_id_for_user(self, session_id: str, user_id: str) -> Optional[Session]:
        """根据id和用户查询会话"""
        stmt = select(SessionModel).where(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id,
        )
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def delete_by_id(self, session_id: str) -> None:
        """根据传递的id删除会话"""
        # 1.构建删除语句
        stmt = delete(SessionModel).where(SessionModel.id == session_id)

        # 2.执行sql无需检查是否删除
        await self.db_session.execute(stmt)

    async def delete_by_id_for_user(self, session_id: str, user_id: str) -> None:
        """根据传递的id和用户删除会话"""
        stmt = delete(SessionModel).where(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id,
        )
        await self.db_session.execute(stmt)

    async def update_title(self, session_id: str, title: str) -> None:
        """更新会话标题"""
        # 1.构建更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(title=title)
        )
        result = await self.db_session.execute(stmt)

        # 2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        """更新会话最新消息"""
        # 1.构建更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                latest_message=message,
                latest_message_at=timestamp,
            )
        )
        result = await self.db_session.execute(stmt)

        # 2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        """往会话中新增事件"""
        # 1.将event序列化为json
        event_data = event.model_dump(mode="json")

        # 2.构建原子更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                events=func.coalesce(SessionModel.events, cast([], JSONB)) + cast([event_data], JSONB),
            )
        )
        result = await self.db_session.execute(stmt)

        # 3.检查是否新增成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def put_next_message(
            self, session_id: str, user_id: str, next_message: NextMessage
    ) -> NextMessage:
        record = await self._get_session_record_for_update(session_id, user_id)
        if record.status != SessionStatus.RUNNING.value:
            raise NextMessageConflictError("会话已不在运行中，请直接发送消息")

        current = (
            NextMessage.model_validate(record.next_message)
            if record.next_message is not None
            else None
        )
        if current is not None and current.state == NextMessageState.PROCESSING:
            raise NextMessageConflictError("排队消息已经开始发送，不能替换")

        queued = next_message.model_copy(
            update={
                "state": NextMessageState.QUEUED,
                "task_id": None,
                "claimed_at": None,
            }
        )
        record.next_message = queued.model_dump(mode="json")
        return queued

    async def cancel_next_message(self, session_id: str, user_id: str) -> None:
        record = await self._get_session_record_for_update(session_id, user_id)
        if record.next_message is None:
            return

        current = NextMessage.model_validate(record.next_message)
        if current.state == NextMessageState.PROCESSING:
            raise NextMessageConflictError("排队消息已经开始发送，不能取消")
        record.next_message = None

    async def finish_or_claim_next_message(
            self, session_id: str, task_id: str
    ) -> Optional[NextMessage]:
        record = await self._get_session_record_for_update(session_id)
        if record.status != SessionStatus.RUNNING.value or record.task_id != task_id:
            raise NextMessageConflictError("当前任务已不是会话的活动任务")
        if record.next_message is None:
            record.status = SessionStatus.COMPLETED.value
            return None

        current = NextMessage.model_validate(record.next_message)
        if current.state == NextMessageState.PROCESSING:
            if current.task_id == task_id:
                return current
            raise NextMessageConflictError("排队消息已被另一个任务认领")

        claimed = current.model_copy(
            update={
                "state": NextMessageState.PROCESSING,
                "task_id": task_id,
                "claimed_at": datetime.now(),
            }
        )
        record.status = SessionStatus.RUNNING.value
        record.next_message = claimed.model_dump(mode="json")
        return claimed

    async def consume_next_message(
            self,
            session_id: str,
            message_id: str,
            task_id: str,
            event: BaseEvent,
    ) -> None:
        record = await self._get_session_record_for_update(session_id)
        if record.next_message is None:
            raise NextMessageConflictError("排队消息已经被消费或取消")

        current = NextMessage.model_validate(record.next_message)
        if (
            current.id != message_id
            or current.state != NextMessageState.PROCESSING
            or current.task_id != task_id
        ):
            raise NextMessageConflictError("排队消息认领状态已经变化")

        record.events = [*(record.events or []), event.model_dump(mode="json")]
        record.next_message = None

    async def start_next_message_run(self, session_id: str, user_id: str) -> Session:
        record = await self._get_session_record_for_update(session_id, user_id)
        if record.status != SessionStatus.COMPLETED.value or record.next_message is None:
            raise NextMessageConflictError("排队消息当前不可恢复执行")

        current = NextMessage.model_validate(record.next_message)
        if current.state != NextMessageState.QUEUED:
            raise NextMessageConflictError("排队消息已经开始发送")
        record.status = SessionStatus.RUNNING.value
        return record.to_domain()

    async def reset_processing_next_message(self, session_id: str) -> Optional[NextMessage]:
        record = await self._get_session_record_for_update(session_id)
        if record.next_message is None:
            return None

        current = NextMessage.model_validate(record.next_message)
        if current.state != NextMessageState.PROCESSING:
            return current

        reset = current.model_copy(
            update={
                "state": NextMessageState.QUEUED,
                "task_id": None,
                "claimed_at": None,
            }
        )
        record.next_message = reset.model_dump(mode="json")
        return reset

    async def resolve_interaction(
            self,
            session_id: str,
            user_id: str,
            action_id: str,
            decision: InteractionDecision,
            answer: Optional[str] = None,
            selected_values: Optional[List[str]] = None,
    ) -> InteractionEvent:
        """Lock the owned session and append exactly one resolved interaction event."""
        stmt = select(SessionModel).where(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id,
        ).with_for_update()
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise InteractionNotFoundError("会话或交互动作不存在")

        session = record.to_domain()
        resolved = session.resolve_interaction(
            action_id=action_id,
            decision=decision,
            answer=answer,
            selected_values=selected_values,
        )
        record.events = [event.model_dump(mode="json") for event in session.events]
        return resolved

    async def add_file(self, session_id: str, file: File) -> None:
        """往会话中新增文件"""
        # 1.将file序列化为json
        file_data = file.model_dump(mode="json")

        # 2.构建原子更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                files=func.coalesce(SessionModel.files, cast([], JSONB)) + cast([file_data], JSONB),
            )
        )
        result = await self.db_session.execute(stmt)

        # 3.检查是否新增成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def remove_file(self, session_id: str, file_id: str) -> None:
        """移除会话中的指定文件"""
        # 1.查询会话记录并加锁
        stmt = select(SessionModel).where(SessionModel.id == session_id).with_for_update()
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        # 2.检查会话记录是否存在
        if not record:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

        # 3.会话记录存在在，则在内存中过滤files
        if not record.files:
            return
        original_length = len(record.files)
        new_files = [file for file in record.files if file.get("id") != file_id]

        # 4.判断文件长度是否有变化
        if len(new_files) == original_length:
            return

        # 5.更新数据
        record.files = new_files

    async def get_file_by_path(self, session_id: str, filepath: str) -> Optional[File]:
        """根据文件路径获取文件信息"""
        # 1.构建语句查询文件列表
        stmt = select(SessionModel.files).where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        files = result.scalar_one_or_none()

        # 2.判断是否为空，如果不存在则返回None
        if not files:
            return None

        # 3.遍历查找数据，如果最后没找到则返回空
        for file in files:
            if file.get("filepath", "") == filepath:
                return File(**file)

        return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        """更新会话状态"""
        # 1.构建更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(status=status.value)
        )
        result = await self.db_session.execute(stmt)

        # 2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        """更新会话的未读消息数"""
        # 1.构建更新语句并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(unread_message_count=count)
        )
        result = await self.db_session.execute(stmt)

        # 2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def increment_unread_message_count(self, session_id: str) -> None:
        """新增会话的未读消息数"""
        # 1.构建新增未读消息数语句并更新
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                unread_message_count=func.coalesce(SessionModel.unread_message_count, 0) + 1,
            )
        )
        result = await self.db_session.execute(stmt)

        # 2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def decrement_unread_message_count(self, session_id: str) -> None:
        """将会话中的未读消息数-1"""
        # 1.构建新增未读消息数语句并更新
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                # 2.核心逻辑：GREATEST((当前值-1), 0)避免出现负数
                unread_message_count=func.greatest(
                    func.coalesce(SessionModel.unread_message_count, 0) - 1,
                    0
                )
            )
        )
        result = await self.db_session.execute(stmt)

        # 3.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def save_memory(self, session_id: str, agent_name: str, memory: Memory) -> None:
        """存储或者更新会话中的记忆(字典直接覆盖)"""
        # 1.将memory转换成为json结构
        memory_data = memory.model_dump(mode="json")

        # 2.构建要打补丁的字典
        patch_data = {agent_name: memory_data}

        # 3.执行合并更新
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                memories=func.coalesce(SessionModel.memories, cast({}, JSONB)) + cast(patch_data, JSONB),
            )
        )
        result = await self.db_session.execute(stmt)

        # 4.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        """获取指定会话的agent记忆信息"""
        # 1.查询会话记忆信息
        stmt = (
            select(SessionModel.memories[agent_name])
            .where(SessionModel.id == session_id)
        )
        result = await self.db_session.execute(stmt)
        memory_data = result.scalar_one_or_none()

        # 2.如果存在记忆则直接返回
        if memory_data:
            return Memory(**memory_data)

        # 3.如果记忆不存在，则构建一个空记忆后返回
        return Memory(messages=[])

    async def get_branch_context_seed(
            self, session_id: str
    ) -> List[BranchContextMessage]:
        """Return only typed user/assistant context generated by branch creation."""
        result = await self.db_session.execute(
            select(SessionModel.context_seed).where(SessionModel.id == session_id)
        )
        raw_seed = result.scalar_one_or_none() or []
        return [
            BranchContextMessage.model_validate(item)
            for item in raw_seed
        ]
