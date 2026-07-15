"""Authenticated cross-resource search service."""
import math
import re
from collections.abc import Callable

from app.repositories.uow import IUnitOfWork
from app.schemas.search import SearchResultItem, SearchResults


class SearchService:
    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        current_page: int = 1,
        page_size: int = 20,
    ) -> SearchResults:
        normalized_query = re.sub(r"\s+", " ", query).strip()
        page = max(1, current_page)
        size = max(1, min(page_size, 50))
        if not normalized_query:
            return SearchResults(
                items=[],
                query="",
                current_page=page,
                page_size=size,
                total_page=0,
                total_record=0,
            )

        uow = self._uow_factory()
        async with uow:
            rows, total = await uow.search.search(
                user_id=user_id,
                query=normalized_query,
                offset=(page - 1) * size,
                limit=size,
            )

        items = []
        for row in rows:
            normalized = {
                **row,
                "title": self._clip(self._normalize_text(row.get("title")), 180),
                "snippet": self._clip(self._normalize_text(row.get("snippet")), 600),
            }
            items.append(SearchResultItem(**normalized))
        return SearchResults(
            items=items,
            query=normalized_query,
            current_page=page,
            page_size=size,
            total_page=math.ceil(total / size) if total else 0,
            total_record=total,
        )

    @staticmethod
    def _normalize_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        return value if len(value) <= limit else f"{value[:limit]}…"
