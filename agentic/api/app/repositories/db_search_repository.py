"""PostgreSQL-backed global search."""
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.search_repository import SearchRepository


SEARCH_SQL = text(r"""
WITH search_items AS (
    SELECT
        'session:' || s.id AS id,
        'session'::text AS content_type,
        s.id AS session_id,
        NULL::text AS run_id,
        NULL::text AS event_id,
        COALESCE(NULLIF(s.title, ''), '未命名任务') AS title,
        COALESCE(NULLIF(s.latest_message, ''), s.title, '') AS snippet,
        COALESCE(s.latest_message_at, s.updated_at, s.created_at) AS created_at,
        jsonb_build_object('status', s.status) AS metadata
    FROM sessions s
    WHERE s.user_id = :user_id
      AND (s.title ILIKE :pattern ESCAPE '\' OR s.latest_message ILIKE :pattern ESCAPE '\')

    UNION ALL

    SELECT
        'message:' || COALESCE(event.value->>'id', md5(s.id || event.ordinality::text)) AS id,
        'message'::text AS content_type,
        s.id AS session_id,
        NULL::text AS run_id,
        event.value->>'id' AS event_id,
        COALESCE(NULLIF(s.title, ''), '未命名任务') AS title,
        COALESCE(event.value->>'message', '') AS snippet,
        COALESCE(s.latest_message_at, s.updated_at, s.created_at) AS created_at,
        jsonb_build_object('role', COALESCE(event.value->>'role', 'assistant')) AS metadata
    FROM sessions s
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(s.events, '[]'::jsonb)) WITH ORDINALITY AS event(value, ordinality)
    WHERE s.user_id = :user_id
      AND event.value->>'type' = 'message'
      AND COALESCE(event.value->>'message', '') ILIKE :pattern ESCAPE '\'

    UNION ALL

    SELECT
        'tool:' || tc.id AS id,
        'tool'::text AS content_type,
        tc.session_id,
        tc.run_id,
        tc.event_id,
        COALESCE(NULLIF(tc.tool_name, ''), NULLIF(tc.function_name, ''), '工具调用') AS title,
        COALESCE(NULLIF(tc.result_preview, ''), NULLIF(tc.arguments_preview, ''), tc.error, '') AS snippet,
        COALESCE(tc.finished_at, tc.started_at, tc.updated_at, tc.created_at) AS created_at,
        jsonb_build_object(
            'function_name', tc.function_name,
            'status', tc.status,
            'executor_type', tc.executor_type
        ) AS metadata
    FROM tool_calls tc
    JOIN agent_runs ar ON ar.id = tc.run_id
    WHERE ar.user_id = :user_id
      AND concat_ws(' ', tc.tool_name, tc.function_name, tc.arguments_preview, tc.result_preview, tc.error)
          ILIKE :pattern ESCAPE '\'

    UNION ALL

    SELECT
        'trace:' || te.id AS id,
        'trace'::text AS content_type,
        te.session_id,
        te.run_id,
        te.event_id,
        te.event_type AS title,
        te.payload::text AS snippet,
        te.created_at,
        jsonb_build_object('source', te.source, 'trace_id', te.trace_id) AS metadata
    FROM trace_events te
    JOIN agent_runs ar ON ar.id = te.run_id
    WHERE ar.user_id = :user_id
      AND concat_ws(' ', te.event_type, te.payload::text) ILIKE :pattern ESCAPE '\'

    UNION ALL

    SELECT
        'file:' || f.id AS id,
        'file'::text AS content_type,
        f.origin_session_id AS session_id,
        f.origin_run_id AS run_id,
        NULL::text AS event_id,
        f.filename AS title,
        concat_ws(' · ', NULLIF(f.extension, ''), NULLIF(f.mime_type, ''), NULLIF(f.source_type, '')) AS snippet,
        COALESCE(f.updated_at, f.created_at) AS created_at,
        jsonb_build_object(
            'file_id', f.id,
            'extension', f.extension,
            'source_type', f.source_type,
            'size', f.size
        ) AS metadata
    FROM files f
    WHERE f.user_id = :user_id
      AND f.status = 'available'
      AND f.entry_type = 'file'
      AND (f.metadata->>'visible' IS NULL OR f.metadata->>'visible' <> 'false')
      AND f.filename ILIKE :pattern ESCAPE '\'
), ranked AS (
    SELECT search_items.*, count(*) OVER() AS _total
    FROM search_items
)
SELECT *
FROM ranked
ORDER BY created_at DESC NULLS LAST, id DESC
OFFSET :offset
LIMIT :limit
""")


class DBSearchRepository(SearchRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        pattern = f"%{self._escape_like(query)}%"
        result = await self.db_session.execute(
            SEARCH_SQL,
            {
                "user_id": user_id,
                "pattern": pattern,
                "offset": max(0, offset),
                "limit": max(1, min(limit, 100)),
            },
        )
        rows = [dict(row) for row in result.mappings().all()]
        total = int(rows[0].pop("_total")) if rows else 0
        for row in rows[1:]:
            row.pop("_total", None)
        return rows, total

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
