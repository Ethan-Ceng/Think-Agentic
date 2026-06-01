from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import get_db_session, get_wechat_service
from app.services.wechat_service import WechatService

router = APIRouter(prefix="/wechat", tags=["wechat"])


@router.api_route("/{app_id}", methods=["GET", "POST"])
async def wechat(
    app_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WechatService = Depends(get_wechat_service),
):
    result = svc.wechat(
        session=session,
        app_id=app_id,
        method=request.method,
        query_params=dict(request.query_params),
        body=await request.body(),
    )
    return Response(content=result, media_type="text/plain")
