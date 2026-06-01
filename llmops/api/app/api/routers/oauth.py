from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_oauth_service
from app.schemas.oauth import AuthorizeRequest
from app.services.oauth_service import OAuthService
from app.shared.response import success_json

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/{provider_name}")
def get_oauth_redirect(
    provider_name: str,
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    oauth = oauth_service.get_oauth_by_provider_name(provider_name)
    return success_json({"redirect_url": oauth.get_authorization_url()})


@router.post("/authorize/{provider_name}")
def authorize(
    provider_name: str,
    req: AuthorizeRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    credential = oauth_service.oauth_login(
        session,
        provider_name,
        req.code,
        request.client.host if request.client else "unknown",
    )
    return success_json(credential)

