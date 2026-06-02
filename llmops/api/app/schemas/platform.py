from uuid import UUID

from pydantic import BaseModel, Field


class UpdateWechatConfigRequest(BaseModel):
    wechat_app_id: str = Field(default="", max_length=255)
    wechat_app_secret: str = Field(default="", max_length=255)
    wechat_token: str = Field(default="", max_length=255)


class WechatConfigResponse(BaseModel):
    id: UUID
    app_id: UUID
    ip: str = ""
    url: str = ""
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_token: str = ""
    status: str = ""
    updated_at: int = 0
    created_at: int = 0

    @classmethod
    def from_config(cls, config, *, ip: str = "", url: str = "") -> "WechatConfigResponse":
        return cls(
            id=config.id,
            app_id=config.app_id,
            ip=ip,
            url=url,
            wechat_app_id=config.wechat_app_id or "",
            wechat_app_secret=config.wechat_app_secret or "",
            wechat_token=config.wechat_token or "",
            status=config.status or "",
            updated_at=int(config.updated_at.timestamp()) if config.updated_at else 0,
            created_at=int(config.created_at.timestamp()) if config.created_at else 0,
        )
