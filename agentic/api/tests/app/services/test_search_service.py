import asyncio
from datetime import datetime

from app.services.search_service import SearchService


class FakeSearchRepository:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search(self, user_id: str, query: str, *, offset: int = 0, limit: int = 20):
        self.calls.append({"user_id": user_id, "query": query, "offset": offset, "limit": limit})
        return [
            {
                "id": "message:event-1",
                "content_type": "message",
                "session_id": "session-1",
                "run_id": None,
                "event_id": "event-1",
                "title": "  研究   任务  ",
                "snippet": "命中\n搜索内容",
                "created_at": datetime(2026, 7, 15, 10, 30),
                "metadata": {"role": "assistant"},
            }
        ], 41


class FakeUow:
    def __init__(self, search: FakeSearchRepository) -> None:
        self.search = search

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def test_search_service_normalizes_query_and_paginates() -> None:
    repository = FakeSearchRepository()
    service = SearchService(lambda: FakeUow(repository))

    async def run() -> None:
        result = await service.search("user-1", "  Agent   搜索  ", current_page=2, page_size=20)
        assert repository.calls == [
            {"user_id": "user-1", "query": "Agent 搜索", "offset": 20, "limit": 20}
        ]
        assert result.total_record == 41
        assert result.total_page == 3
        assert result.items[0].title == "研究 任务"
        assert result.items[0].snippet == "命中 搜索内容"

    asyncio.run(run())


def test_search_service_skips_repository_for_blank_query() -> None:
    repository = FakeSearchRepository()
    service = SearchService(lambda: FakeUow(repository))

    async def run() -> None:
        result = await service.search("user-1", "   ")
        assert repository.calls == []
        assert result.items == []
        assert result.total_record == 0

    asyncio.run(run())
