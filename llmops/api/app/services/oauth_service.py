from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundException
from app.integrations.oauth import GithubOAuth, OAuth
from app.models.account import AccountOAuth
from app.services.account_service import AccountService
from app.services.base_service import BaseService
from app.services.jwt_service import JwtService


@dataclass
class OAuthService(BaseService):
    settings: Settings
    jwt_service: JwtService
    account_service: AccountService

    def get_all_oauth(self) -> dict[str, OAuth]:
        github = GithubOAuth(
            client_id=self.settings.github_client_id,
            client_secret=self.settings.github_client_secret,
            redirect_uri=self.settings.github_redirect_uri,
        )
        return {"github": github}

    def get_oauth_by_provider_name(self, provider_name: str) -> OAuth:
        oauth = self.get_all_oauth().get(provider_name)
        if oauth is None:
            raise NotFoundException(f"OAuth provider [{provider_name}] does not exist")
        return oauth

    def oauth_login(self, session: Session, provider_name: str, code: str, remote_addr: str) -> dict[str, Any]:
        oauth = self.get_oauth_by_provider_name(provider_name)
        oauth_access_token = oauth.get_access_token(code)
        oauth_user_info = oauth.get_user_info(oauth_access_token)

        account_oauth = self.account_service.get_account_oauth_by_provider_name_and_openid(
            session,
            provider_name,
            oauth_user_info.id,
        )
        if not account_oauth:
            account = self.account_service.get_account_by_email(session, oauth_user_info.email)
            if not account:
                account = self.account_service.create_account(
                    session,
                    name=oauth_user_info.name,
                    email=oauth_user_info.email,
                )
            account_oauth = self.create(
                session,
                AccountOAuth,
                account_id=account.id,
                provider=provider_name,
                openid=oauth_user_info.id,
                encrypted_token=oauth_access_token,
            )
        else:
            account = self.account_service.get_account(session, account_oauth.account_id)

        self.update(session, account, last_login_at=datetime.now(), last_login_ip=remote_addr)
        self.update(session, account_oauth, encrypted_token=oauth_access_token)

        expire_at = int((datetime.now() + timedelta(days=30)).timestamp())
        access_token = self.jwt_service.generate_token({"sub": str(account.id), "iss": "llmops", "exp": expire_at})
        return {"expire_at": expire_at, "access_token": access_token}

