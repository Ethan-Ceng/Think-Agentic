import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.agent import AgentQueueManager, AgentThought, QueueEvent
from app.core.app import AppStatus
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.account import Account
from app.models.app import AppConfig, AppDatasetJoin
from app.models.conversation import Conversation, Message
from app.models.end_user import EndUser
from app.services.app_service import AppService
from app.services.base_service import BaseService
from app.shared.response import Response


@dataclass
class OpenAPIService(BaseService):
    app_service: AppService = field(default_factory=AppService)

    def chat(self, session: Session, req, account: Account):
        app = self.app_service.get_app(session, req.app_id, account)
        if app.status != AppStatus.PUBLISHED.value or not app.app_config_id:
            raise NotFoundException("App does not exist or is not published")

        end_user = self._get_or_create_end_user(session, app.id, req.end_user_id, account)
        conversation = self._get_or_create_conversation(session, app.id, req.conversation_id, end_user)
        config = self._get_published_runtime_config(session, app.app_config_id, app.id)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.SERVICE_API.value,
            created_by=end_user.id,
            query=req.query,
            image_urls=req.image_urls,
            status=MessageStatus.NORMAL.value,
        )
        task_id = uuid4()
        AgentQueueManager.register_task(task_id, InvokeFrom.SERVICE_API, account.id)

        if req.stream:
            return self._stream_chat(session, task_id, conversation, message, config, req, account, end_user.id, app)

        thoughts = list(
            self.app_service._run_debug_agent(session, task_id, conversation, message, config, req, account)
        )
        self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
        AgentQueueManager.clear_task(task_id)
        return Response(data=self._response_data(message, end_user.id, conversation.id, req, thoughts))

    def _stream_chat(
        self,
        session: Session,
        task_id: UUID,
        conversation: Conversation,
        message: Message,
        config: dict,
        req,
        account: Account,
        end_user_id: UUID,
        app,
    ):
        thoughts: list[AgentThought] = []
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
                yield self._format_openapi_sse(thought, end_user_id, conversation.id, message.id)
                if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                    break
        finally:
            self.app_service._save_agent_result(session, account, app, conversation, message, thoughts)
            AgentQueueManager.clear_task(task_id)

    def _get_or_create_end_user(
        self,
        session: Session,
        app_id: UUID,
        end_user_id: UUID | None,
        account: Account,
    ) -> EndUser:
        if end_user_id:
            end_user = session.get(EndUser, end_user_id)
            if end_user is None or end_user.app_id != app_id or end_user.tenant_id != account.id:
                raise ForbiddenException("End user does not belong to this app")
            return end_user
        return self.create(session, EndUser, tenant_id=account.id, app_id=app_id)

    def _get_or_create_conversation(
        self,
        session: Session,
        app_id: UUID,
        conversation_id: UUID | None,
        end_user: EndUser,
    ) -> Conversation:
        if conversation_id:
            conversation = session.get(Conversation, conversation_id)
            if (
                conversation is None
                or conversation.app_id != app_id
                or conversation.invoke_from != InvokeFrom.SERVICE_API.value
                or conversation.created_by != end_user.id
                or conversation.is_deleted
            ):
                raise ForbiddenException("Conversation does not belong to this app or end user")
            return conversation
        return self.create(
            session,
            Conversation,
            app_id=app_id,
            name="New Conversation",
            invoke_from=InvokeFrom.SERVICE_API.value,
            created_by=end_user.id,
        )

    def _get_published_runtime_config(self, session: Session, app_config_id: UUID, app_id: UUID) -> dict:
        app_config = session.get(AppConfig, app_config_id)
        if app_config is None:
            raise NotFoundException("Published app config does not exist")
        config = self.app_service._config_to_dict(app_config)
        config["datasets"] = [
            str(row.dataset_id)
            for row in session.query(AppDatasetJoin).filter(AppDatasetJoin.app_id == app_id).all()
        ]
        return config

    @staticmethod
    def _format_openapi_sse(
        thought: AgentThought,
        end_user_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
    ) -> str:
        data = {
            **thought.model_dump(
                mode="json",
                include={"event", "thought", "observation", "tool", "tool_input", "answer", "latency"},
            ),
            "id": str(thought.id),
            "end_user_id": str(end_user_id),
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "task_id": str(thought.task_id),
        }
        return f"event: {thought.event.value}\ndata:{json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _response_data(message: Message, end_user_id: UUID, conversation_id: UUID, req, thoughts: list[AgentThought]):
        return {
            "id": str(message.id),
            "end_user_id": str(end_user_id),
            "conversation_id": str(conversation_id),
            "query": req.query,
            "image_urls": req.image_urls,
            "answer": "".join(thought.answer for thought in thoughts if thought.event == QueueEvent.AGENT_MESSAGE),
            "total_token_count": max((thought.total_token_count for thought in thoughts), default=0),
            "latency": max((thought.latency for thought in thoughts), default=0.0),
            "agent_thoughts": [
                {
                    "id": str(thought.id),
                    "event": thought.event.value,
                    "thought": thought.thought,
                    "observation": thought.observation,
                    "tool": thought.tool,
                    "tool_input": thought.tool_input,
                    "latency": thought.latency,
                    "created_at": 0,
                }
                for thought in thoughts
                if thought.event != QueueEvent.PING
            ],
        }
