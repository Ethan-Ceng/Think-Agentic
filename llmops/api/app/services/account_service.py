import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import FailException
from app.models.account import Account, AccountOAuth
from app.services.base_service import BaseService
from app.services.jwt_service import JwtService
from app.shared.password import compare_password, hash_password


@dataclass
class AccountService(BaseService):
    jwt_service: JwtService

    def get_account(self, session: Session, account_id: UUID) -> Account | None:
        return self.get(session, Account, account_id)

    def get_account_oauth_by_provider_name_and_openid(
        self,
        session: Session,
        provider_name: str,
        openid: str,
    ) -> AccountOAuth | None:
        return (
            session.query(AccountOAuth)
            .filter(
                AccountOAuth.provider == provider_name,
                AccountOAuth.openid == openid,
            )
            .one_or_none()
        )

    def get_account_by_email(self, session: Session, email: str) -> Account | None:
        return session.query(Account).filter(Account.email == email).one_or_none()

    def get_account_by_token(self, session: Session, token: str) -> Account | None:
        try:
            payload = self.jwt_service.parse_token(token)
            account_id = UUID(payload.get("sub"))
            return self.get_account(session, account_id)
        except Exception:
            return None

    def create_account(self, session: Session, **kwargs: Any) -> Account:
        return self.create(session, Account, **kwargs)

    def update_password(self, session: Session, password: str, account: Account) -> Account:
        salt = secrets.token_bytes(16)
        base64_salt = base64.b64encode(salt).decode()
        password_hashed = hash_password(password, salt)
        base64_password_hashed = base64.b64encode(password_hashed).decode()
        return self.update_account(session, account, password=base64_password_hashed, password_salt=base64_salt)

    def update_account(self, session: Session, account: Account, **kwargs: Any) -> Account:
        return self.update(session, account, **kwargs)

    def password_login(self, session: Session, email: str, password: str, remote_addr: str) -> dict[str, Any]:
        account = self.get_account_by_email(session, email)
        if not account:
            raise FailException("Account does not exist or password is incorrect")

        if not account.is_password_set or not compare_password(password, account.password, account.password_salt):
            raise FailException("Account does not exist or password is incorrect")

        expire_at = int((datetime.now() + timedelta(days=30)).timestamp())
        access_token = self.jwt_service.generate_token(
            {
                "sub": str(account.id),
                "iss": "llmops",
                "exp": expire_at,
            }
        )
        self.update(session, account, last_login_at=datetime.now(), last_login_ip=remote_addr)

        return {
            "expire_at": expire_at,
            "access_token": access_token,
        }

