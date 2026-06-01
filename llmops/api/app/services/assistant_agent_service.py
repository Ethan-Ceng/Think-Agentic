from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.core.agent import AgentQueueManager, QueueEvent
from app.core.app import DEFAULT_APP_CONFIG
from app.core.config import Settings, get_settings
from app.core.conversation import InvokeFrom, MessageStatus
from app.models.account import Account
from app.models.conversation import Conversation, Message
from app.services.app_service import AppService
from app.services.base_service import BaseService

ASSISTANT_AGENT_PROMPT = """You are the platform assistant for this LLMOps project.
Help users design agents, workflows, tools, datasets, prompts, and integration plans.
When the user asks to create an app automatically, use the create_app tool with a concise name and detailed
description."""


@dataclass
class AssistantAgentService(BaseService):
    app_service: AppService = field(default_factory=AppService)
    settings: Settings = field(default_factory=get_settings)

    def chat(self, session: Session, req, account: Account):
        assistant_agent_id = self._assistant_agent_id()
        conversation = self._get_assistant_agent_conversation(session, account, assistant_agent_id)
        message = self.create(
            session,
            Message,
            app_id=assistant_agent_id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.ASSISTANT_AGENT.value,
            created_by=account.id,
            query=req.query,
            image_urls=req.image_urls,
            status=MessageStatus.NORMAL.value,
        )
        config = self._assistant_runtime_config()
        task_id = uuid4()
        AgentQueueManager.register_task(task_id, InvokeFrom.ASSISTANT_AGENT, account.id)

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
            pseudo_app = SimpleNamespace(id=assistant_agent_id)
            self.app_service._save_agent_result(session, account, pseudo_app, conversation, message, thoughts)
            AgentQueueManager.clear_task(task_id)

    def stop_chat(self, task_id: UUID, account: Account) -> None:
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.ASSISTANT_AGENT, account.id)

    def get_conversation_messages_with_page(self, session: Session, req, account: Account):
        conversation = self._get_assistant_agent_conversation(session, account, self._assistant_agent_id())
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
        if req.created_at:
            query = query.filter(Message.created_at <= datetime.fromtimestamp(req.created_at))

        total_record = query.count()
        total_page = (total_record + req.page_size - 1) // req.page_size if total_record else 0
        messages = (
            query.order_by(desc(Message.created_at))
            .offset((req.page - 1) * req.page_size)
            .limit(req.page_size)
            .all()
        )
        return list(messages), total_record, total_page

    def delete_conversation(self, session: Session, account: Account) -> None:
        if account.assistant_agent_conversation_id:
            self.update(session, account, assistant_agent_conversation_id=None)

    def _get_assistant_agent_conversation(
        self,
        session: Session,
        account: Account,
        assistant_agent_id: UUID,
    ) -> Conversation:
        if account.assistant_agent_conversation_id:
            conversation = session.get(Conversation, account.assistant_agent_conversation_id)
            if conversation is not None and not conversation.is_deleted:
                return conversation

        conversation = self.create(
            session,
            Conversation,
            app_id=assistant_agent_id,
            name="New Conversation",
            invoke_from=InvokeFrom.ASSISTANT_AGENT.value,
            created_by=account.id,
        )
        self.update(session, account, assistant_agent_conversation_id=conversation.id)
        return conversation

    @staticmethod
    def _assistant_runtime_config() -> dict:
        config = deepcopy(DEFAULT_APP_CONFIG)
        config["dialog_round"] = 3
        config["preset_prompt"] = ASSISTANT_AGENT_PROMPT
        config["long_term_memory"] = {"enable": True}
        config["runtime_capabilities"] = [{"type": "create_app"}]
        return config

    def _assistant_agent_id(self) -> UUID:
        return UUID(self.settings.assistant_agent_id or "00000000-0000-0000-0000-000000000000")
