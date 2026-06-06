import math
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.core.agent import AgentQueueManager, QueueEvent
from app.core.app import AppStatus
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.account import Account
from app.models.app import App, AppConfig, AppDatasetJoin
from app.models.conversation import Conversation, Message
from app.models.end_user import EndUser
from app.models.task import AgentTask
from app.services.app_service import AppService
from app.services.base_service import BaseService
from app.services.language_model_service import LanguageModelService

WAITING_TASK_STATUSES = {"waiting", "waiting_user", "waiting_approval"}


@dataclass
class WebAppService(BaseService):
    app_service: AppService = field(default_factory=AppService)

    def get_web_app(self, session: Session, token: str) -> App:
        app = session.query(App).filter(App.token == token).one_or_none()
        if app is None or app.status != AppStatus.PUBLISHED.value:
            raise NotFoundException("Web app does not exist or is not published")
        return app

    def get_web_app_info(self, session: Session, token: str, end_user_id: UUID | None) -> tuple[EndUser, dict]:
        app = self.get_web_app(session, token)
        end_user = self._get_or_create_end_user(session, app, end_user_id)
        config = self._get_published_runtime_config(session, app)
        app_account = self._get_app_account(session, app)
        llm = LanguageModelService().load_language_model(config.get("model_config", {}), session, app_account)
        return (
            end_user,
            {
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
            },
        )

    def web_app_chat(self, session: Session, token: str, req, end_user_id: UUID | None):
        app = self.get_web_app(session, token)
        account = self._get_app_account(session, app)
        end_user = self._get_or_create_end_user(session, app, end_user_id)
        conversation = self._get_or_create_conversation(session, app.id, req.conversation_id, end_user)
        config = self._get_published_runtime_config(session, app)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.WEB_APP.value,
            created_by=end_user.id,
            query=req.query,
            image_urls=req.image_urls,
            status=MessageStatus.NORMAL.value,
        )
        if (getattr(app, "agent_type", "worker") or "worker") == "planner":
            resume_task_id = req.resume_task_id or self._latest_waiting_planner_task_id(
                session,
                account=account,
                end_user=end_user,
                conversation=conversation,
            )
            if resume_task_id is not None:
                return end_user, self._web_app_planner_resume_stream(
                    session,
                    app=app,
                    account=account,
                    end_user=end_user,
                    conversation=conversation,
                    message=message,
                    task_id=resume_task_id,
                    query=req.query,
                    image_urls=req.image_urls,
                )
            return end_user, self._web_app_planner_stream(
                session,
                app=app,
                account=account,
                end_user=end_user,
                conversation=conversation,
                message=message,
                query=req.query,
                image_urls=req.image_urls,
                config=config,
            )

        task_id = uuid4()
        AgentQueueManager.register_task(task_id, InvokeFrom.WEB_APP, end_user.id)

        def stream():
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
                    for runtime_event in self.app_service.chat_runtime_event_service.events_from_agent_thought(
                        thought,
                        conversation_id=conversation.id,
                        message_id=message.id,
                    ):
                        yield self.app_service._format_runtime_event_sse(runtime_event)
                    if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                        break
            finally:
                self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
                AgentQueueManager.clear_task(task_id)

        return end_user, stream()

    def _web_app_planner_stream(
        self,
        session: Session,
        *,
        app: App,
        account: Account,
        end_user: EndUser,
        conversation: Conversation,
        message: Message,
        query: str,
        image_urls: list[str],
        config: dict,
    ):
        from app.services.router_agent_manager_service import RouterAgentManagerService

        task_id: UUID | None = None
        thoughts = []

        def register_task(created_task_id: UUID) -> None:
            nonlocal task_id
            task_id = created_task_id
            AgentQueueManager.register_task(created_task_id, InvokeFrom.WEB_APP, end_user.id)

        def stream():
            nonlocal task_id
            router_service = RouterAgentManagerService(app_service=self.app_service)
            try:
                recent_history = router_service._conversation_recent_history(
                    session,
                    conversation.id,
                    int(config.get("dialog_round") or 3),
                )
                for stream_event in router_service.stream_planner_run(
                    session,
                    planner_app_id=app.id,
                    query=query,
                    account=account,
                    conversation=conversation,
                    message=message,
                    invoke_from=InvokeFrom.WEB_APP,
                    created_by=end_user.id,
                    recent_history=recent_history,
                    image_urls=image_urls,
                    on_task_created=register_task,
                    is_stopped=AgentQueueManager.is_stopped,
                ):
                    thought = stream_event.thought
                    task_id = thought.task_id
                    thoughts.append(thought)
                    yield self.app_service._format_agent_sse(thought, conversation.id, message.id)
                    for runtime_event in self.app_service.chat_runtime_event_service.events_from_agent_thought(
                        thought,
                        conversation_id=conversation.id,
                        message_id=message.id,
                    ):
                        yield self.app_service._format_runtime_event_sse(runtime_event)
                    if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                        break
            finally:
                self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
                if task_id is not None:
                    AgentQueueManager.clear_task(task_id)

        return stream()

    def _web_app_planner_resume_stream(
        self,
        session: Session,
        *,
        app: App,
        account: Account,
        end_user: EndUser,
        conversation: Conversation,
        message: Message,
        task_id: UUID,
        query: str,
        image_urls: list[str],
    ):
        from app.services.router_agent_manager_service import RouterAgentManagerService

        thoughts = []

        def stream():
            AgentQueueManager.register_task(task_id, InvokeFrom.WEB_APP, end_user.id)
            router_service = RouterAgentManagerService(app_service=self.app_service)
            try:
                for stream_event in router_service.resume_planner_run(
                    session,
                    task_id=task_id,
                    account=account,
                    query=query,
                    conversation=conversation,
                    message=message,
                    invoke_from=InvokeFrom.WEB_APP,
                    created_by=end_user.id,
                    image_urls=image_urls,
                    is_stopped=AgentQueueManager.is_stopped,
                ):
                    thought = stream_event.thought
                    thoughts.append(thought)
                    yield self.app_service._format_agent_sse(thought, conversation.id, message.id)
                    for runtime_event in self.app_service.chat_runtime_event_service.events_from_agent_thought(
                        thought,
                        conversation_id=conversation.id,
                        message_id=message.id,
                    ):
                        yield self.app_service._format_runtime_event_sse(runtime_event)
                    if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                        break
            finally:
                self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
                AgentQueueManager.clear_task(task_id)

        return stream()

    def stop_web_app_chat(self, session: Session, token: str, task_id: UUID, end_user_id: UUID | None) -> None:
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, end_user.id)

    def get_conversation_messages_with_page(
        self,
        session: Session,
        token: str,
        conversation_id: UUID,
        end_user_id: UUID | None,
        created_at: int = 0,
        current_page: int = 1,
        page_size: int = 20,
    ):
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        conversation = self._get_conversation(session, app.id, conversation_id, end_user)
        query = (
            session.query(Message)
            .options(selectinload(Message.agent_thoughts))
            .filter(
                Message.conversation_id == conversation.id,
                Message.status.in_([MessageStatus.STOP.value, MessageStatus.NORMAL.value]),
                Message.answer != "",
                Message.is_deleted.is_(False),
            )
        )
        if created_at:
            query = query.filter(Message.created_at <= datetime.fromtimestamp(created_at))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        messages = (
            query.order_by(desc(Message.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return end_user, list(messages), total_record, total_page

    def delete_conversation(
        self,
        session: Session,
        token: str,
        conversation_id: UUID,
        end_user_id: UUID | None,
    ) -> None:
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        conversation = self._get_conversation(session, app.id, conversation_id, end_user)
        self.update(session, conversation, is_deleted=True)

    def update_conversation_is_pinned(
        self,
        session: Session,
        token: str,
        conversation_id: UUID,
        end_user_id: UUID | None,
        is_pinned: bool,
    ) -> None:
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        conversation = self._get_conversation(session, app.id, conversation_id, end_user)
        self.update(session, conversation, is_pinned=is_pinned)

    def update_conversation_name(
        self,
        session: Session,
        token: str,
        conversation_id: UUID,
        end_user_id: UUID | None,
        name: str,
    ) -> None:
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        conversation = self._get_conversation(session, app.id, conversation_id, end_user)
        self.update(session, conversation, name=name)

    def generate_suggested_questions(
        self,
        session: Session,
        token: str,
        message_id: UUID,
        end_user_id: UUID | None,
    ) -> tuple[EndUser, list[str]]:
        app = self.get_web_app(session, token)
        end_user = self._get_existing_end_user(session, app, end_user_id)
        message = session.get(Message, message_id)
        if (
            message is None
            or message.app_id != app.id
            or message.invoke_from != InvokeFrom.WEB_APP.value
            or message.created_by != end_user.id
            or message.is_deleted
        ):
            raise ForbiddenException("Message does not belong to this web app visitor")

        subject = (message.query or "this topic").strip()[:80]
        return (
            end_user,
            [
                f"Can you explain more about {subject}?",
                "What are the next practical steps?",
                "Are there any risks or alternatives I should consider?",
            ],
        )

    def get_conversations(
        self,
        session: Session,
        token: str,
        is_pinned: bool,
        end_user_id: UUID | None,
    ) -> tuple[EndUser, list[Conversation]]:
        app = self.get_web_app(session, token)
        end_user = self._get_or_create_end_user(session, app, end_user_id)
        return (
            end_user,
            list(
                session.query(Conversation)
                .filter(
                    Conversation.app_id == app.id,
                    Conversation.created_by == end_user.id,
                    Conversation.invoke_from == InvokeFrom.WEB_APP.value,
                    Conversation.is_pinned == is_pinned,
                    Conversation.is_deleted.is_(False),
                )
                .order_by(desc(Conversation.created_at))
                .all()
            )
        )

    def _get_app_account(self, session: Session, app: App) -> Account:
        account = session.get(Account, app.account_id)
        if account is None:
            raise NotFoundException("Web app owner does not exist")
        return account

    def _get_or_create_end_user(self, session: Session, app: App, end_user_id: UUID | None) -> EndUser:
        if end_user_id:
            end_user = session.get(EndUser, end_user_id)
            if end_user is not None and end_user.app_id == app.id and end_user.tenant_id == app.account_id:
                return end_user
        return self.create(session, EndUser, tenant_id=app.account_id, app_id=app.id)

    def _latest_waiting_planner_task_id(
        self,
        session: Session,
        *,
        account: Account,
        end_user: EndUser,
        conversation: Conversation,
    ) -> UUID | None:
        task = (
            session.query(AgentTask)
            .filter(
                AgentTask.tenant_id == account.id,
                AgentTask.conversation_id == conversation.id,
                AgentTask.user_id == end_user.id,
                AgentTask.status.in_(list(WAITING_TASK_STATUSES)),
            )
            .order_by(desc(AgentTask.updated_at), desc(AgentTask.created_at))
            .first()
        )
        return task.id if task is not None else None

    def _get_existing_end_user(self, session: Session, app: App, end_user_id: UUID | None) -> EndUser:
        if end_user_id:
            end_user = session.get(EndUser, end_user_id)
            if end_user is not None and end_user.app_id == app.id and end_user.tenant_id == app.account_id:
                return end_user
        raise ForbiddenException("Web app visitor is not initialized")

    def _get_conversation(
        self,
        session: Session,
        app_id: UUID,
        conversation_id: UUID,
        end_user: EndUser,
    ) -> Conversation:
        conversation = session.get(Conversation, conversation_id)
        if (
            conversation is None
            or conversation.app_id != app_id
            or conversation.invoke_from != InvokeFrom.WEB_APP.value
            or conversation.created_by != end_user.id
            or conversation.is_deleted
        ):
            raise ForbiddenException("Conversation does not belong to this web app")
        return conversation

    def _get_or_create_conversation(
        self,
        session: Session,
        app_id: UUID,
        conversation_id: UUID | None,
        end_user: EndUser,
    ) -> Conversation:
        if conversation_id:
            return self._get_conversation(session, app_id, conversation_id, end_user)
        return self.create(
            session,
            Conversation,
            app_id=app_id,
            name="New Conversation",
            invoke_from=InvokeFrom.WEB_APP.value,
            created_by=end_user.id,
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
