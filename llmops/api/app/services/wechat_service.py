import hashlib
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.app import AppStatus
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import FailException
from app.core.platform import WechatConfigStatus
from app.models.account import Account
from app.models.app import App, AppConfig, AppDatasetJoin
from app.models.conversation import Conversation, Message
from app.models.end_user import EndUser
from app.models.platform import WechatConfig, WechatEndUser, WechatMessage
from app.services.app_service import AppService
from app.services.base_service import BaseService


@dataclass
class WechatService(BaseService):
    app_service: AppService = field(default_factory=AppService)

    def wechat(self, session: Session, app_id: UUID, method: str, query_params: dict[str, str], body: bytes) -> str:
        app = session.get(App, app_id)
        if app is None or app.status != AppStatus.PUBLISHED.value:
            if method == "GET":
                raise FailException("App is not published")
            return self._reply_text("Service", "User", "App is not published")

        wechat_config = session.query(WechatConfig).filter(WechatConfig.app_id == app.id).one_or_none()
        if wechat_config is None or wechat_config.status != WechatConfigStatus.CONFIGURED.value:
            if method == "GET":
                raise FailException("Wechat is not configured")
            return self._reply_text("Service", "User", "Wechat is not configured")

        if method == "GET":
            return self._verify_wechat_signature(wechat_config, query_params)
        return self._handle_text_message(session, app, wechat_config, body)

    def _handle_text_message(self, session: Session, app: App, wechat_config: WechatConfig, body: bytes) -> str:
        incoming = self._parse_message(body)
        if incoming["msg_type"] != "text":
            return self._reply_text(incoming["from_user"], incoming["to_user"], "Only text messages are supported")

        openid = incoming["from_user"]
        content = incoming["content"].strip()
        wechat_end_user = self._get_or_create_wechat_end_user(session, app, openid)
        conversation = self._get_or_create_conversation(session, app.id, wechat_end_user.end_user_id)

        if content == "1":
            pending = (
                session.query(WechatMessage)
                .filter(WechatMessage.wechat_end_user_id == wechat_end_user.id)
                .order_by(desc(WechatMessage.created_at))
                .first()
            )
            if pending and not pending.is_pushed:
                message = session.get(Message, pending.message_id)
                if message and message.answer:
                    self.update(session, pending, is_pushed=True)
                    return self._reply_text(incoming["from_user"], incoming["to_user"], message.answer)
                return self._reply_text(incoming["from_user"], incoming["to_user"], "The task is still processing")

        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.SERVICE_API.value,
            created_by=wechat_end_user.end_user_id,
            query=content,
            image_urls=[],
            status=MessageStatus.NORMAL.value,
        )
        wechat_message = self.create(
            session,
            WechatMessage,
            wechat_end_user_id=wechat_end_user.id,
            message_id=message.id,
            is_pushed=False,
        )

        answer = self._run_app_chat(session, app, conversation, message, content)
        self.update(session, wechat_message, is_pushed=True)
        return self._reply_text(incoming["from_user"], incoming["to_user"], answer)

    def _run_app_chat(
        self,
        session: Session,
        app: App,
        conversation: Conversation,
        message: Message,
        query: str,
    ) -> str:
        app_config = self._get_published_runtime_config(session, app)
        account = session.get(Account, app.account_id)
        if account is None:
            return "App owner does not exist"

        req = SimpleNamespace(query=query, image_urls=[])
        thoughts = list(
            self.app_service._run_debug_agent(
                session,
                message.id,
                conversation,
                message,
                app_config,
                req,
                account,
            )
        )
        self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
        answer = "".join(thought.answer for thought in thoughts if thought.event.value == "agent_message")
        error = next((thought.observation for thought in thoughts if thought.event.value == "error"), "")
        return answer or error or "No answer was generated"

    def _get_or_create_wechat_end_user(self, session: Session, app: App, openid: str) -> WechatEndUser:
        wechat_end_user = (
            session.query(WechatEndUser)
            .filter(WechatEndUser.openid == openid, WechatEndUser.app_id == app.id)
            .one_or_none()
        )
        if wechat_end_user is not None:
            return wechat_end_user

        end_user = self.create(session, EndUser, tenant_id=app.account_id, app_id=app.id)
        return self.create(
            session,
            WechatEndUser,
            openid=openid,
            app_id=app.id,
            end_user_id=end_user.id,
        )

    def _get_or_create_conversation(self, session: Session, app_id: UUID, end_user_id: UUID) -> Conversation:
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.app_id == app_id,
                Conversation.created_by == end_user_id,
                Conversation.invoke_from == InvokeFrom.SERVICE_API.value,
                Conversation.is_deleted.is_(False),
            )
            .one_or_none()
        )
        if conversation is not None:
            return conversation
        return self.create(
            session,
            Conversation,
            app_id=app_id,
            name="New Conversation",
            invoke_from=InvokeFrom.SERVICE_API.value,
            created_by=end_user_id,
        )

    def _get_published_runtime_config(self, session: Session, app: App) -> dict:
        if not app.app_config_id:
            raise FailException("Published app config does not exist")
        app_config = session.get(AppConfig, app.app_config_id)
        if app_config is None:
            raise FailException("Published app config does not exist")
        config = self.app_service._config_to_dict(app_config)
        config["datasets"] = [
            str(row.dataset_id)
            for row in session.query(AppDatasetJoin).filter(AppDatasetJoin.app_id == app.id).all()
        ]
        return config

    @classmethod
    def _verify_wechat_signature(cls, config: WechatConfig, query_params: dict[str, str]) -> str:
        signature = query_params.get("signature", "")
        timestamp = query_params.get("timestamp", "")
        nonce = query_params.get("nonce", "")
        echostr = query_params.get("echostr", "")
        expected = hashlib.sha1("".join(sorted([config.wechat_token or "", timestamp, nonce])).encode()).hexdigest()
        if signature != expected:
            raise FailException("Wechat signature verification failed")
        return echostr

    @staticmethod
    def _parse_message(body: bytes) -> dict[str, str]:
        root = ET.fromstring(body)
        data = {child.tag: child.text or "" for child in root}
        return {
            "to_user": data.get("ToUserName", ""),
            "from_user": data.get("FromUserName", ""),
            "msg_type": data.get("MsgType", ""),
            "content": data.get("Content", ""),
        }

    @staticmethod
    def _reply_text(to_user: str, from_user: str, content: str) -> str:
        return (
            "<xml>"
            f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
            f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
            f"<CreateTime>{int(time.time())}</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            f"<Content><![CDATA[{content}]]></Content>"
            "</xml>"
        )
