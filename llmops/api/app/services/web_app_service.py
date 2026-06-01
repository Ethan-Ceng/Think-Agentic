from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.agent import AgentQueueManager, QueueEvent
from app.core.app import AppStatus
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.account import Account
from app.models.app import App, AppConfig, AppDatasetJoin
from app.models.conversation import Conversation, Message
from app.services.app_service import AppService
from app.services.base_service import BaseService
from app.services.language_model_service import LanguageModelService


@dataclass
class WebAppService(BaseService):
    app_service: AppService = field(default_factory=AppService)

    def get_web_app(self, session: Session, token: str) -> App:
        app = session.query(App).filter(App.token == token).one_or_none()
        if app is None or app.status != AppStatus.PUBLISHED.value:
            raise NotFoundException("Web app does not exist or is not published")
        return app

    def get_web_app_info(self, session: Session, token: str) -> dict:
        app = self.get_web_app(session, token)
        config = self._get_published_runtime_config(session, app)
        llm = LanguageModelService().load_language_model(config.get("model_config", {}))
        return {
            "id": str(app.id),
            "icon": app.icon,
            "name": app.name,
            "description": app.description,
            "app_config": {
                "opening_statement": config.get("opening_statement"),
                "opening_questions": config.get("opening_questions"),
                "suggested_after_answer": config.get("suggested_after_answer"),
                "features": [feature.value for feature in llm.features],
                "text_to_speech": config.get("text_to_speech"),
                "speech_to_text": config.get("speech_to_text"),
            },
        }

    def web_app_chat(self, session: Session, token: str, req, account: Account):
        app = self.get_web_app(session, token)
        conversation = self._get_or_create_conversation(session, app.id, req.conversation_id, account)
        config = self._get_published_runtime_config(session, app)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.WEB_APP.value,
            created_by=account.id,
            query=req.query,
            image_urls=req.image_urls,
            status=MessageStatus.NORMAL.value,
        )
        task_id = uuid4()
        AgentQueueManager.register_task(task_id, InvokeFrom.WEB_APP, account.id)

        thoughts = []
        try:
            for thought in self.app_service._run_debug_agent(
                session,
                task_id,
                conversation,
                message,
                config,
                req,
                account,
            ):
                thoughts.append(thought)
                yield self.app_service._format_agent_sse(thought, conversation.id, message.id)
                if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                    break
        finally:
            self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
            AgentQueueManager.clear_task(task_id)

    def stop_web_app_chat(self, session: Session, token: str, task_id: UUID, account: Account) -> None:
        self.get_web_app(session, token)
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, account.id)

    def get_conversations(self, session: Session, token: str, is_pinned: bool, account: Account) -> list[Conversation]:
        app = self.get_web_app(session, token)
        return list(
            session.query(Conversation)
            .filter(
                Conversation.app_id == app.id,
                Conversation.created_by == account.id,
                Conversation.invoke_from == InvokeFrom.WEB_APP.value,
                Conversation.is_pinned == is_pinned,
                Conversation.is_deleted.is_(False),
            )
            .order_by(desc(Conversation.created_at))
            .all()
        )

    def _get_or_create_conversation(
        self,
        session: Session,
        app_id: UUID,
        conversation_id: UUID | None,
        account: Account,
    ) -> Conversation:
        if conversation_id:
            conversation = session.get(Conversation, conversation_id)
            if (
                conversation is None
                or conversation.app_id != app_id
                or conversation.invoke_from != InvokeFrom.WEB_APP.value
                or conversation.created_by != account.id
                or conversation.is_deleted
            ):
                raise ForbiddenException("Conversation does not belong to this web app")
            return conversation
        return self.create(
            session,
            Conversation,
            app_id=app_id,
            name="New Conversation",
            invoke_from=InvokeFrom.WEB_APP.value,
            created_by=account.id,
        )

    def _get_published_runtime_config(self, session: Session, app: App) -> dict:
        if not app.app_config_id:
            raise NotFoundException("Published app config does not exist")
        app_config = session.get(AppConfig, app.app_config_id)
        if app_config is None:
            raise NotFoundException("Published app config does not exist")
        config = self.app_service._config_to_dict(app_config)
        config["datasets"] = [
            str(row.dataset_id)
            for row in session.query(AppDatasetJoin).filter(AppDatasetJoin.app_id == app.id).all()
        ]
        return config
