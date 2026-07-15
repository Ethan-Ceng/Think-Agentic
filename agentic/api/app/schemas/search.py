"""Global search response schemas."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SearchContentType = Literal["session", "message", "tool", "trace", "file"]


class SearchResultItem(BaseModel):
    id: str
    content_type: SearchContentType
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    event_id: Optional[str] = None
    title: str
    snippet: str
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResults(BaseModel):
    items: List[SearchResultItem] = Field(default_factory=list)
    query: str
    current_page: int
    page_size: int
    total_page: int
    total_record: int
