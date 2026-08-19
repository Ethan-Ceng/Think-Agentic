#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Database-backed run/trace repository."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentRunModel,
    ModelCallModel,
    RunSkillModel,
    RunStepModel,
    ToolCallModel,
    TraceEventModel,
)
from app.repositories.trace_repository import TraceRepository


class DBTraceRepository(TraceRepository):
    """PostgreSQL run/trace repository."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def create_run(self, data: Dict[str, Any]) -> None:
        self.db_session.add(AgentRunModel(**data))

    async def update_run(self, run_id: str, data: Dict[str, Any]) -> None:
        if not data:
            return
        await self.db_session.execute(
            update(AgentRunModel)
            .where(AgentRunModel.id == run_id)
            .values(**self._with_updated_at(data))
        )

    async def upsert_step(self, run_id: str, step_id: str, data: Dict[str, Any]) -> str:
        result = await self.db_session.execute(
            select(RunStepModel).where(
                RunStepModel.run_id == run_id,
                RunStepModel.step_id == step_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = RunStepModel(**data)
            self.db_session.add(record)
            return record.id

        for key, value in self._with_updated_at(data).items():
            setattr(record, key, value)
        return record.id

    async def upsert_tool_call(self, run_id: str, tool_call_id: str, data: Dict[str, Any]) -> str:
        result = await self.db_session.execute(
            select(ToolCallModel).where(
                ToolCallModel.run_id == run_id,
                ToolCallModel.tool_call_id == tool_call_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = ToolCallModel(**data)
            self.db_session.add(record)
            return record.id

        for key, value in self._with_updated_at(data).items():
            setattr(record, key, value)
        return record.id

    async def create_model_call(self, data: Dict[str, Any]) -> None:
        self.db_session.add(ModelCallModel(**data))

    async def update_model_call(self, model_call_id: str, data: Dict[str, Any]) -> None:
        if not data:
            return
        await self.db_session.execute(
            update(ModelCallModel)
            .where(ModelCallModel.id == model_call_id)
            .values(**self._with_updated_at(data))
        )

    async def append_event(self, data: Dict[str, Any]) -> int:
        record = TraceEventModel(**data)
        self.db_session.add(record)
        await self.db_session.flush()
        return record.ingest_seq

    async def save_run_skill(self, data: Dict[str, Any]) -> None:
        self.db_session.add(RunSkillModel(**data))

    async def finalize_interrupted_run(
        self,
        session_id: str,
        error: str,
        finished_at: datetime,
    ) -> Optional[str]:
        result = await self.db_session.execute(
            select(AgentRunModel)
            .where(
                AgentRunModel.session_id == session_id,
                AgentRunModel.status.in_(("pending", "running", "waiting")),
            )
            .order_by(AgentRunModel.created_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None

        await self.db_session.execute(
            update(AgentRunModel)
            .where(AgentRunModel.id == run.id)
            .values(status="failed", error=error, finished_at=finished_at, updated_at=finished_at)
        )
        await self.db_session.execute(
            update(RunStepModel)
            .where(
                RunStepModel.run_id == run.id,
                RunStepModel.status.notin_(("completed", "failed")),
            )
            .values(
                status="failed",
                success=False,
                error=error,
                finished_at=finished_at,
                updated_at=finished_at,
            )
        )
        await self.db_session.execute(
            update(ToolCallModel)
            .where(ToolCallModel.run_id == run.id, ToolCallModel.status == "calling")
            .values(
                status="failed",
                success=False,
                error=error,
                finished_at=finished_at,
                updated_at=finished_at,
            )
        )
        await self.db_session.execute(
            update(ModelCallModel)
            .where(ModelCallModel.run_id == run.id, ModelCallModel.status == "started")
            .values(status="failed", error=error, finished_at=finished_at, updated_at=finished_at)
        )
        self.db_session.add(
            TraceEventModel(
                trace_id=run.trace_id,
                run_id=run.id,
                session_id=session_id,
                event_type="run.interrupted",
                source="system",
                payload={"error": error, "reason": "task_registry_lost"},
                created_at=finished_at,
            )
        )
        return run.id

    async def list_runs(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        stmt = select(AgentRunModel).where(AgentRunModel.user_id == user_id)
        if session_id:
            stmt = stmt.where(AgentRunModel.session_id == session_id)
        stmt = stmt.order_by(AgentRunModel.created_at.desc()).limit(limit)
        result = await self.db_session.execute(stmt)
        return [self._to_dict(record) for record in result.scalars().all()]

    async def get_run(self, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        result = await self.db_session.execute(
            select(AgentRunModel).where(
                AgentRunModel.id == run_id,
                AgentRunModel.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        return self._to_dict(record) if record is not None else None

    async def list_trace_events(
        self,
        run_id: str,
        after: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        stmt = select(TraceEventModel).where(TraceEventModel.run_id == run_id)
        if after is not None:
            stmt = stmt.where(TraceEventModel.ingest_seq > after)
        result = await self.db_session.execute(
            stmt.order_by(TraceEventModel.ingest_seq.asc()).limit(limit)
        )
        return [self._to_dict(record) for record in result.scalars().all()]

    async def list_steps(self, run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        result = await self.db_session.execute(
            select(RunStepModel)
            .where(RunStepModel.run_id == run_id)
            .order_by(RunStepModel.created_at.asc(), RunStepModel.id.asc())
            .limit(limit)
        )
        return [self._to_dict(record) for record in result.scalars().all()]

    async def list_tool_calls(
        self,
        run_id: str,
        after: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        cursor = await self._record_cursor(ToolCallModel, run_id, after)
        if after and cursor is None:
            return []
        stmt = select(ToolCallModel).where(ToolCallModel.run_id == run_id)
        if cursor is not None:
            created_at, record_id = cursor
            stmt = stmt.where(
                or_(
                    ToolCallModel.created_at > created_at,
                    and_(
                        ToolCallModel.created_at == created_at,
                        ToolCallModel.id > record_id,
                    ),
                )
            )
        result = await self.db_session.execute(
            stmt.order_by(ToolCallModel.created_at.asc(), ToolCallModel.id.asc()).limit(limit)
        )
        return [self._to_dict(record) for record in result.scalars().all()]

    async def list_model_calls(
        self,
        run_id: str,
        after: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        cursor = await self._record_cursor(ModelCallModel, run_id, after)
        if after and cursor is None:
            return []
        stmt = select(ModelCallModel).where(ModelCallModel.run_id == run_id)
        if cursor is not None:
            created_at, record_id = cursor
            stmt = stmt.where(
                or_(
                    ModelCallModel.created_at > created_at,
                    and_(
                        ModelCallModel.created_at == created_at,
                        ModelCallModel.id > record_id,
                    ),
                )
            )
        result = await self.db_session.execute(
            stmt.order_by(ModelCallModel.created_at.asc(), ModelCallModel.id.asc()).limit(limit)
        )
        return [self._to_dict(record) for record in result.scalars().all()]

    async def list_run_skills(
        self, user_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        result = await self.db_session.execute(
            select(RunSkillModel)
            .join(AgentRunModel, AgentRunModel.id == RunSkillModel.run_id)
            .where(
                AgentRunModel.user_id == user_id,
                RunSkillModel.run_id == run_id,
            )
            .order_by(RunSkillModel.created_at.asc(), RunSkillModel.id.asc())
        )
        return [self._to_dict(record) for record in result.scalars().all()]

    @classmethod
    def _with_updated_at(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        return {**data, "updated_at": datetime.now()}

    async def _record_cursor(
        self,
        model: Any,
        run_id: str,
        record_id: Optional[str],
    ) -> Optional[tuple[datetime, str]]:
        if not record_id:
            return None
        result = await self.db_session.execute(
            select(model.created_at, model.id).where(
                model.run_id == run_id,
                model.id == record_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        return row.created_at, row.id

    @classmethod
    def _to_dict(cls, record: Any) -> Dict[str, Any]:
        return {
            column.name: getattr(record, column.name)
            for column in record.__table__.columns
        }
