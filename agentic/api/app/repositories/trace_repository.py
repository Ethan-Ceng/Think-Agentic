#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run/trace repository protocol."""
from typing import Any, Dict, List, Optional, Protocol


class TraceRepository(Protocol):
    """Persistence boundary for run and trace records."""

    async def create_run(self, data: Dict[str, Any]) -> None:
        ...

    async def update_run(self, run_id: str, data: Dict[str, Any]) -> None:
        ...

    async def upsert_step(self, run_id: str, step_id: str, data: Dict[str, Any]) -> str:
        ...

    async def upsert_tool_call(self, run_id: str, tool_call_id: str, data: Dict[str, Any]) -> str:
        ...

    async def create_model_call(self, data: Dict[str, Any]) -> None:
        ...

    async def update_model_call(self, model_call_id: str, data: Dict[str, Any]) -> None:
        ...

    async def append_event(self, data: Dict[str, Any]) -> None:
        ...

    async def save_run_skill(self, data: Dict[str, Any]) -> None:
        ...

    async def finalize_interrupted_run(
        self,
        session_id: str,
        error: str,
        finished_at: Any,
    ) -> Optional[str]:
        """Fail the latest active run and all of its unfinished child records."""
        ...

    async def list_runs(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        ...

    async def get_run(self, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def list_trace_events(self, run_id: str) -> List[Dict[str, Any]]:
        ...

    async def list_steps(self, run_id: str) -> List[Dict[str, Any]]:
        ...

    async def list_tool_calls(self, run_id: str) -> List[Dict[str, Any]]:
        ...

    async def list_model_calls(self, run_id: str) -> List[Dict[str, Any]]:
        ...

    async def list_run_skills(
        self, user_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        ...
