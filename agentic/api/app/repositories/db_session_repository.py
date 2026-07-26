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
from sqlalchemy.orm.attributes import set_committed_value

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
    SessionBranchFamilyValidationError,
    SessionBranchNotFoundError,
    SessionOrganizationConflictError,
    SessionOrganizationNotFoundError,
    SessionStatus,
)
from app.repositories.session_repository import SessionBranchFamily, SessionRepository
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
        if source.archived_at is not None:
            raise SessionBranchConflictError("归档会话恢复后才能创建分支")

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
            project_id=source.project_id,
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

    async def get_branch_family(
            self,
            session_id: str,
            user_id: str,
            target_event_id: Optional[str] = None,
    ) -> SessionBranchFamily:
        """Resolve an owned direct branch family without mutating session state."""
        current_result = await self.db_session.execute(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
        )
        current = current_result.scalar_one_or_none()
        if current is None:
            raise SessionBranchNotFoundError("会话不存在或无权访问")

        explicit_source_target = (
            target_event_id is not None
            and self._has_visible_message(current, target_event_id)
        )
        source: Optional[SessionModel]
        if current.source_session_id is not None and not explicit_source_target:
            canonical_target = current.forked_from_event_id
            if canonical_target is None:
                raise SessionBranchConflictError("分支会话缺少来源锚点")
            if (
                target_event_id is not None
                and target_event_id != canonical_target
            ):
                raise SessionBranchConflictError("目标消息锚点与分支来源不一致")

            family_source_id = current.source_session_id
            source_result = await self.db_session.execute(
                select(SessionModel).where(
                    SessionModel.id == family_source_id,
                    SessionModel.user_id == user_id,
                )
            )
            source = source_result.scalar_one_or_none()
            if (
                source is not None
                and not self._has_visible_message(source, canonical_target)
            ):
                raise SessionBranchConflictError("分支来源锚点不存在或不可见")
        else:
            if target_event_id is None:
                raise SessionBranchFamilyValidationError("必须提供目标消息 ID")
            if not explicit_source_target:
                if current.source_session_id is not None:
                    raise SessionBranchConflictError("目标消息锚点与分支来源不一致")
                raise SessionBranchNotFoundError("目标消息不存在或不可见")

            canonical_target = target_event_id
            family_source_id = current.id
            source = current

        children_result = await self.db_session.execute(
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.source_session_id == family_source_id,
                SessionModel.forked_from_event_id == canonical_target,
            )
            .order_by(
                SessionModel.created_at.asc(),
                SessionModel.id.asc(),
            )
        )
        children = sorted(
            children_result.scalars().all(),
            key=lambda record: (record.created_at, record.id),
        )

        if current.id != family_source_id and all(
            child.id != current.id for child in children
        ):
            raise SessionBranchConflictError("当前会话不在计算出的分支族中")

        source_domain = source.to_domain() if source is not None else None
        child_domains = tuple(child.to_domain() for child in children)
        variants = (
            (source_domain, *child_domains)
            if source_domain is not None
            else child_domains
        )
        current_domain = next(
            (
                variant
                for variant in variants
                if variant.id == current.id
            ),
            None,
        )
        if current_domain is None:
            raise SessionBranchConflictError("当前会话不在计算出的分支族中")

        return SessionBranchFamily(
            source_session=source_domain,
            target_event_id=canonical_target,
            current_session=current_domain,
            variants=variants,
        )

    @staticmethod
    def _has_visible_message(record: SessionModel, event_id: str) -> bool:
        return any(
            isinstance(raw_event, dict)
            and raw_event.get("id") == event_id
            and raw_event.get("type") == "message"
            and raw_event.get("visible", True)
            and raw_event.get("role") in {"user", "assistant"}
            for raw_event in (record.events or [])
        )

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

    async def get_all_by_user(
            self, user_id: str, archived: bool = False
    ) -> List[Session]:
        """获取指定用户的会话列表"""
        stmt = select(SessionModel).where(
            SessionModel.user_id == user_id,
            (
                SessionModel.archived_at.is_not(None)
                if archived
                else SessionModel.archived_at.is_(None)
            ),
        )
        if archived:
            stmt = stmt.order_by(
                SessionModel.archived_at.desc(),
                SessionModel.created_at.desc(),
            )
        else:
            stmt = stmt.order_by(
                SessionModel.is_pinned.desc(),
                SessionModel.latest_message_at.desc().nullslast(),
                SessionModel.created_at.desc(),
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
        """兼容旧调用；自动标题不得覆盖手工标题。"""
        await self.update_generated_title(session_id, title)

    async def update_generated_title(self, session_id: str, title: str) -> bool:
        """Update an Agent-generated title only while the title is not user-owned."""
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.title_is_manual.is_(False),
            )
            .values(title=title)
        )
        result = await self.db_session.execute(stmt)
        return bool(result.rowcount)

    async def update_manual_title(
            self, session_id: str, user_id: str, title: str
    ) -> Session:
        """Set and lock a user-owned title."""
        return await self.update_organization(
            session_id,
            user_id,
            title=title,
        )

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
        """Atomically update user-owned navigation metadata."""
        result = await self.db_session.execute(
            select(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise SessionOrganizationNotFoundError("会话不存在或无权访问")

        is_currently_archived = record.archived_at is not None
        will_be_archived = (
            archived if archived is not None else is_currently_archived
        )
        if pinned is True and will_be_archived:
            raise SessionOrganizationConflictError("已归档会话不能置顶")
        if (
            archived is True
            and not is_currently_archived
            and (
                record.status
                in {SessionStatus.RUNNING.value, SessionStatus.WAITING.value}
                or record.next_message is not None
            )
        ):
            raise SessionOrganizationConflictError(
                "运行中、等待中或存在排队消息的会话不能归档"
            )

        values = {}
        if title is not None:
            values["title"] = title
            values["title_is_manual"] = True
        if archived is True:
            values["archived_at"] = record.archived_at or datetime.now()
            values["is_pinned"] = False
        elif archived is False:
            values["archived_at"] = None
        if pinned is not None:
            values["is_pinned"] = pinned
        if project_id_provided:
            values["project_id"] = project_id

        if not values:
            return record.to_domain()

        # Organization metadata is navigation state, not conversation activity.
        # Explicitly carrying the current value suppresses SessionModel.updated_at
        # client-side onupdate while retaining one atomic row-locked write.
        values["updated_at"] = record.updated_at
        update_result = await self.db_session.execute(
            update(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
            .values(**values)
        )
        if update_result.rowcount == 0:
            raise SessionOrganizationNotFoundError("会话不存在或无权访问")
        for field_name, value in values.items():
            set_committed_value(record, field_name, value)
        return record.to_domain()

    async def claim_execution(
            self,
            session_id: str,
            user_id: str,
    ) -> tuple[Session, Optional[SessionStatus]]:
        """Serialize starting a Run with archive transitions on the same row lock."""
        result = await self.db_session.execute(
            select(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise SessionOrganizationNotFoundError("会话不存在或无权访问")
        if record.archived_at is not None:
            raise SessionOrganizationConflictError(
                "任务已归档，请先恢复后再继续执行"
            )

        if record.status == SessionStatus.RUNNING.value:
            return record.to_domain(), None

        previous_status = SessionStatus(record.status)
        record.status = SessionStatus.RUNNING.value
        await self.db_session.flush()
        return record.to_domain(), previous_status

    async def update_runtime_handles(
            self,
            session_id: str,
            *,
            sandbox_id: Optional[str] = None,
            task_id: Optional[str] = None,
    ) -> None:
        """Patch runtime handles without writing a stale Session aggregate."""
        values = {
            field_name: value
            for field_name, value in (
                ("sandbox_id", sandbox_id),
                ("task_id", task_id),
            )
            if value is not None
        }
        if not values:
            return

        result = await self.db_session.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(**values)
        )
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
        if record.archived_at is not None:
            raise NextMessageConflictError("任务已归档，请先恢复后再继续执行")
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
        if record.archived_at is not None:
            raise NextMessageConflictError("任务已归档，请先恢复后再继续执行")
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
