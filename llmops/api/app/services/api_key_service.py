import math
import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException
from app.models.account import Account
from app.models.api_key import ApiKey
from app.services.base_service import BaseService


@dataclass
class ApiKeyService(BaseService):
    def create_api_key(
        self,
        session: Session,
        account: Account,
        is_active: bool = True,
        remark: str = "",
    ) -> ApiKey:
        return self.create(
            session,
            ApiKey,
            account_id=account.id,
            api_key=self.generate_api_key(),
            is_active=is_active,
            remark=remark,
        )

    def get_api_key(self, session: Session, api_key_id: UUID, account: Account) -> ApiKey:
        api_key = self.get(session, ApiKey, api_key_id)
        if not api_key or api_key.account_id != account.id:
            raise ForbiddenException("API key does not exist or no permission")
        return api_key

    def get_api_key_by_credential(self, session: Session, api_key: str) -> ApiKey | None:
        return session.query(ApiKey).filter(ApiKey.api_key == api_key).one_or_none()

    def update_api_key(self, session: Session, api_key_id: UUID, account: Account, **kwargs) -> ApiKey:
        api_key = self.get_api_key(session, api_key_id, account)
        return self.update(session, api_key, **kwargs)

    def delete_api_key(self, session: Session, api_key_id: UUID, account: Account) -> ApiKey:
        api_key = self.get_api_key(session, api_key_id, account)
        return self.delete(session, api_key)

    def get_api_keys_with_page(
        self,
        session: Session,
        account: Account,
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ApiKey], int, int]:
        query = session.query(ApiKey).filter(ApiKey.account_id == account.id)
        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        api_keys = (
            query.order_by(desc(ApiKey.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(api_keys), total_record, total_page

    @classmethod
    def generate_api_key(cls, api_key_prefix: str = "llmops-v1/") -> str:
        return api_key_prefix + secrets.token_urlsafe(48)

