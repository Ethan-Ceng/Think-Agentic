from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.app import AppStatus
from app.core.platform import WechatConfigStatus
from app.models.account import Account
from app.models.platform import WechatConfig
from app.services.app_service import AppService
from app.services.base_service import BaseService


@dataclass
class PlatformService(BaseService):
    app_service: AppService = field(default_factory=AppService)

    def get_wechat_config(self, session: Session, app_id: UUID, account: Account) -> WechatConfig:
        app = self.app_service.get_app(session, app_id, account)
        wechat_config = session.query(WechatConfig).filter(WechatConfig.app_id == app.id).one_or_none()
        if wechat_config is None:
            wechat_config = self.create(
                session,
                WechatConfig,
                app_id=app.id,
                status=WechatConfigStatus.UNCONFIGURED.value,
            )
        return wechat_config

    def update_wechat_config(
        self,
        session: Session,
        app_id: UUID,
        account: Account,
        wechat_app_id: str,
        wechat_app_secret: str,
        wechat_token: str,
    ) -> WechatConfig:
        app = self.app_service.get_app(session, app_id, account)
        wechat_config = session.query(WechatConfig).filter(WechatConfig.app_id == app.id).one_or_none()
        if wechat_config is None:
            wechat_config = self.create(session, WechatConfig, app_id=app.id)

        status = WechatConfigStatus.UNCONFIGURED.value
        if wechat_app_id and wechat_app_secret and wechat_token and app.status == AppStatus.PUBLISHED.value:
            status = WechatConfigStatus.CONFIGURED.value

        return self.update(
            session,
            wechat_config,
            wechat_app_id=wechat_app_id,
            wechat_app_secret=wechat_app_secret,
            wechat_token=wechat_token,
            status=status,
        )
