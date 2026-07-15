"""Global search repository protocol."""
from typing import Any, Dict, List, Protocol, Tuple


class SearchRepository(Protocol):
    async def search(
        self,
        user_id: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        ...
