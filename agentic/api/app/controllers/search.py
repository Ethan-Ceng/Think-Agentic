"""Authenticated global search controller."""
from fastapi import APIRouter, Depends, Query

from app.core.entities.user import User
from app.dependencies import get_current_user, get_search_service
from app.schemas import Response
from app.schemas.search import SearchResults
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["全局搜索"])


@router.get("", summary="跨任务、消息、工具、Trace 和文件搜索")
async def global_search(
    q: str = Query(default="", max_length=200),
    current_page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> Response[SearchResults]:
    results = await service.search(
        user_id=current_user.id,
        query=q,
        current_page=current_page,
        page_size=page_size,
    )
    return Response.success(data=results)
