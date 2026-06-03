import base64
import json
import random
import re
import string
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID, uuid4

from sqlalchemy import delete as sql_delete
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, selectinload

from app.core.agent import AgentQueueManager, AgentThought, QueueEvent
from app.core.app import DEFAULT_APP_CONFIG, AppConfigType, AppStatus
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import FailException, NotFoundException, ValidateErrorException
from app.core.language_model.chat_runtime import ChatCompletionRuntime, ChatToolCall
from app.core.language_model.entities import BaseLanguageModel, ModelFeature
from app.core.memory import TokenBufferMemory
from app.core.tools.api_tools.entities import ToolEntity
from app.core.tools.api_tools.providers import ApiProviderManager
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.core.tools.builtin_tools.runtime import get_tool_params
from app.models.account import Account
from app.models.api_tool import ApiTool
from app.models.app import App, AppConfig, AppConfigVersion, AppDatasetJoin
from app.models.conversation import Conversation, Message, MessageAgentThought
from app.models.dataset import Dataset
from app.models.file import File
from app.models.workflow import Workflow
from app.services.agent_adapter_service import LegacyAppWorkerAdapter, WorkerAgentDescriptor
from app.services.base_service import BaseService
from app.services.capability_adapter_service import ToolCapabilityAdapter
from app.services.dataset_service import DatasetService
from app.services.language_model_service import LanguageModelService
from app.services.storage_service import StorageService
from app.services.workflow_service import WorkflowService

MAX_AGENT_ITERATION_RESPONSE = "Current agent iteration count exceeded the limit. Please retry."
AUTO_CREATED_APP_ICON_URL = "https://dummyimage.com/512x512/2563eb/ffffff.png&text=AI"


@dataclass(frozen=True)
class RuntimeCapability:
    name: str
    description: str
    parameters: dict[str, Any]
    kind: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppService(BaseService):
    capability_adapter: ToolCapabilityAdapter = field(default_factory=ToolCapabilityAdapter)
    worker_agent_adapter: LegacyAppWorkerAdapter = field(default_factory=LegacyAppWorkerAdapter)
    storage_service: StorageService = field(default_factory=StorageService)

    def auto_create_app(self, session: Session, name: str, description: str, account_id: UUID) -> App:
        account = session.get(Account, account_id)
        if account is None:
            raise NotFoundException("Account does not exist")

        app = self.create(
            session,
            App,
            account_id=account.id,
            name=name[:40],
            icon=AUTO_CREATED_APP_ICON_URL,
            description=description[:800],
            status=AppStatus.DRAFT.value,
        )
        config = {
            **deepcopy(DEFAULT_APP_CONFIG),
            "preset_prompt": self._auto_created_app_prompt(name, description),
            "opening_statement": "Hello, how can I help you?",
        }
        draft = self._create_config_version(
            session,
            app.id,
            version=0,
            config_type=AppConfigType.DRAFT.value,
            config=config,
        )
        self.update(session, app, draft_app_config_id=draft.id)
        return app

    def create_app(self, session: Session, req, account: Account) -> App:
        app = self.create(
            session,
            App,
            account_id=account.id,
            name=req.name,
            icon=req.icon,
            description=req.description,
            status=AppStatus.DRAFT.value,
        )
        draft = self._create_config_version(
            session,
            app.id,
            version=0,
            config_type=AppConfigType.DRAFT.value,
            config=deepcopy(DEFAULT_APP_CONFIG),
        )
        self.update(session, app, draft_app_config_id=draft.id)
        return app

    def get_app(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get(session, App, app_id)
        if app is None or app.account_id != account.id:
            raise NotFoundException("App does not exist")
        return app

    def update_app(self, session: Session, app_id: UUID, req, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        return self.update(session, app, **req.model_dump())

    def copy_app(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        draft = self.get_or_create_draft_config(session, app)
        new_app = self.create(
            session,
            App,
            account_id=account.id,
            name=f"{app.name} Copy",
            icon=app.icon,
            description=app.description,
            status=AppStatus.DRAFT.value,
        )
        new_draft = self._create_config_version(
            session,
            new_app.id,
            version=0,
            config_type=AppConfigType.DRAFT.value,
            config=self._config_to_dict(draft),
        )
        self.update(session, new_app, draft_app_config_id=new_draft.id)
        return new_app

    def delete_app(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        session.execute(sql_delete(AppDatasetJoin).where(AppDatasetJoin.app_id == app.id))
        session.execute(sql_delete(AppConfig).where(AppConfig.app_id == app.id))
        session.execute(sql_delete(AppConfigVersion).where(AppConfigVersion.app_id == app.id))
        self.delete(session, app)
        return app

    def app_to_worker_agent_descriptor(self, session: Session, app_id: UUID, account: Account) -> WorkerAgentDescriptor:
        app = self.get_app(session, app_id, account)
        config = self.get_or_create_draft_config(session, app)
        return self.worker_agent_adapter.app_to_worker_descriptor(app, self._config_to_dict(config))

    def get_apps_with_page(self, session: Session, req, account: Account) -> tuple[list[App], int, int]:
        query = session.query(App).filter(App.account_id == account.id)
        if req.search_word:
            query = query.filter(App.name.ilike(f"%{req.search_word}%"))
        total_record = query.count()
        total_page = (total_record + req.page_size - 1) // req.page_size if total_record else 0
        apps = query.order_by(desc(App.created_at)).offset((req.page - 1) * req.page_size).limit(req.page_size).all()
        return list(apps), total_record, total_page

    def get_or_create_draft_config(self, session: Session, app: App) -> AppConfigVersion:
        draft = (
            session.query(AppConfigVersion)
            .filter(AppConfigVersion.app_id == app.id, AppConfigVersion.config_type == AppConfigType.DRAFT.value)
            .one_or_none()
        )
        if draft is None:
            draft = self._create_config_version(
                session,
                app.id,
                version=0,
                config_type=AppConfigType.DRAFT.value,
                config=deepcopy(DEFAULT_APP_CONFIG),
            )
            self.update(session, app, draft_app_config_id=draft.id)
        return draft

    def get_active_config_for_page(self, session: Session, app: App):
        if app.status == AppStatus.PUBLISHED.value and app.app_config_id:
            app_config = self.get(session, AppConfig, app.app_config_id)
            if app_config:
                return app_config
        return self.get_or_create_draft_config(session, app)

    def get_draft_app_config(self, session: Session, app_id: UUID, account: Account) -> dict[str, Any]:
        app = self.get_app(session, app_id, account)
        draft = self.get_or_create_draft_config(session, app)
        return self._config_to_response(session, draft)

    def update_draft_app_config(
        self,
        session: Session,
        app_id: UUID,
        draft_app_config: dict[str, Any],
        account: Account,
    ) -> AppConfigVersion:
        app = self.get_app(session, app_id, account)
        draft = self.get_or_create_draft_config(session, app)
        config = self._validate_config(
            session,
            {
                **self._config_to_dict(draft),
                **(draft_app_config or {}),
            },
            account,
        )
        return self.update(session, draft, **config)

    def publish_draft_app_config(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        draft = self.get_or_create_draft_config(session, app)
        config = self._config_to_dict(draft)
        app_config = self.create(
            session,
            AppConfig,
            app_id=app.id,
            model_config=config["model_config"],
            dialog_round=config["dialog_round"],
            preset_prompt=config["preset_prompt"],
            tools=config["tools"],
            workflows=config["workflows"],
            retrieval_config=config["retrieval_config"],
            long_term_memory=config["long_term_memory"],
            opening_statement=config["opening_statement"],
            opening_questions=config["opening_questions"],
            speech_to_text=config["speech_to_text"],
            text_to_speech=config["text_to_speech"],
            suggested_after_answer=config["suggested_after_answer"],
            review_config=config["review_config"],
        )
        session.execute(sql_delete(AppDatasetJoin).where(AppDatasetJoin.app_id == app.id))
        for dataset_id in config["datasets"]:
            self.create(session, AppDatasetJoin, app_id=app.id, dataset_id=dataset_id)

        max_version = (
            session.query(func.coalesce(func.max(AppConfigVersion.version), 0))
            .filter(AppConfigVersion.app_id == app.id, AppConfigVersion.config_type == AppConfigType.PUBLISHED.value)
            .scalar()
        )
        self._create_config_version(
            session,
            app.id,
            version=int(max_version or 0) + 1,
            config_type=AppConfigType.PUBLISHED.value,
            config=config,
        )
        return self.update(
            session,
            app,
            app_config_id=app_config.id,
            status=AppStatus.PUBLISHED.value,
        )

    def cancel_publish_app_config(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        if app.status != AppStatus.PUBLISHED.value:
            raise FailException("App is not published")
        session.execute(sql_delete(AppDatasetJoin).where(AppDatasetJoin.app_id == app.id))
        return self.update(session, app, app_config_id=None, status=AppStatus.DRAFT.value)

    def get_publish_histories_with_page(self, session: Session, app_id: UUID, req, account: Account):
        app = self.get_app(session, app_id, account)
        query = session.query(AppConfigVersion).filter(
            AppConfigVersion.app_id == app.id,
            AppConfigVersion.config_type == AppConfigType.PUBLISHED.value,
        )
        total_record = query.count()
        total_page = (total_record + req.page_size - 1) // req.page_size if total_record else 0
        versions = (
            query.order_by(desc(AppConfigVersion.version))
            .offset((req.page - 1) * req.page_size)
            .limit(req.page_size)
            .all()
        )
        return list(versions), total_record, total_page

    def fallback_history_to_draft(
        self,
        session: Session,
        app_id: UUID,
        app_config_version_id: UUID,
        account: Account,
    ) -> AppConfigVersion:
        app = self.get_app(session, app_id, account)
        version = self.get(session, AppConfigVersion, app_config_version_id)
        if version is None or version.app_id != app.id:
            raise NotFoundException("App config version does not exist")
        draft = self.get_or_create_draft_config(session, app)
        return self.update(session, draft, **self._config_to_dict(version))

    def get_published_config(self, session: Session, app_id: UUID, account: Account) -> dict[str, Any]:
        app = self.get_app(session, app_id, account)
        response: dict[str, Any] = {}
        if app.app_config_id:
            app_config = self.get(session, AppConfig, app.app_config_id)
            if app_config:
                response = self._config_to_response(session, app_config)

        response["web_app"] = {
            "token": app.token or "",
            "status": AppStatus.PUBLISHED.value if app.status == AppStatus.PUBLISHED.value else AppStatus.DRAFT.value,
        }
        return response

    def regenerate_web_app_token(self, session: Session, app_id: UUID, account: Account) -> str:
        app = self.get_app(session, app_id, account)
        token = self._generate_random_string(16)
        self.update(session, app, token=token)
        return token

    def get_debug_conversation_summary(self, session: Session, app_id: UUID, account: Account) -> str:
        app = self.get_app(session, app_id, account)
        config = self._config_to_dict(self.get_or_create_draft_config(session, app))
        if not config["long_term_memory"].get("enable", False):
            raise FailException("Long term memory is not enabled")
        return self._get_or_create_debug_conversation(session, app, account).summary

    def update_debug_conversation_summary(
        self,
        session: Session,
        app_id: UUID,
        summary: str,
        account: Account,
    ) -> Conversation:
        app = self.get_app(session, app_id, account)
        config = self._config_to_dict(self.get_or_create_draft_config(session, app))
        if not config["long_term_memory"].get("enable", False):
            raise FailException("Long term memory is not enabled")
        conversation = self._get_or_create_debug_conversation(session, app, account)
        return self.update(session, conversation, summary=summary)

    def delete_debug_conversation(self, session: Session, app_id: UUID, account: Account) -> App:
        app = self.get_app(session, app_id, account)
        if app.debug_conversation_id:
            self.update(session, app, debug_conversation_id=None)
        return app

    def debug_chat(self, session: Session, app_id: UUID, req, account: Account):
        app = self.get_app(session, app_id, account)
        config = self._config_to_dict(self.get_or_create_draft_config(session, app))
        conversation = self._get_or_create_debug_conversation(session, app, account)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.DEBUGGER.value,
            created_by=account.id,
            query=req.query,
            image_urls=req.image_urls,
            status=MessageStatus.NORMAL.value,
        )
        task_id = uuid4()
        AgentQueueManager.register_task(task_id, InvokeFrom.DEBUGGER, account.id)

        agent_thoughts: list[AgentThought] = []
        try:
            for thought in self._run_debug_agent(session, task_id, conversation, message, config, req, account):
                agent_thoughts.append(thought)
                yield self._format_agent_sse(thought, conversation.id, message.id)
                if thought.event in {QueueEvent.AGENT_END, QueueEvent.ERROR, QueueEvent.STOP, QueueEvent.TIMEOUT}:
                    break
        finally:
            self._save_agent_result(session, account, app, conversation, message, agent_thoughts)
            AgentQueueManager.clear_task(task_id)

    def stop_debug_chat(self, session: Session, app_id: UUID, task_id: UUID, account: Account) -> None:
        self.get_app(session, app_id, account)
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, account.id)

    def get_debug_conversation_messages_with_page(self, session: Session, app_id: UUID, req, account: Account):
        app = self.get_app(session, app_id, account)
        conversation = self._get_or_create_debug_conversation(session, app, account)
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
            from datetime import datetime

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

    def _get_or_create_debug_conversation(self, session: Session, app: App, account: Account) -> Conversation:
        if app.debug_conversation_id:
            conversation = session.get(Conversation, app.debug_conversation_id)
            if conversation is not None and not conversation.is_deleted:
                return conversation

        conversation = self.create(
            session,
            Conversation,
            app_id=app.id,
            name=app.name,
            summary="",
            invoke_from=InvokeFrom.DEBUGGER.value,
            created_by=account.id,
        )
        self.update(session, app, debug_conversation_id=conversation.id)
        return conversation

    def _run_debug_agent(
        self,
        session: Session,
        task_id: UUID,
        conversation: Conversation,
        message: Message,
        config: dict[str, Any],
        req,
        account: Account,
    ):
        yield from self.run_app_agent(
            session=session,
            task_id=task_id,
            config=config,
            query=req.query,
            image_urls=req.image_urls,
            account=account,
            conversation_id=conversation.id,
            conversation_summary=conversation.summary,
        )

    def run_app_worker(
        self,
        session: Session,
        *,
        app_id: UUID,
        task_id: UUID,
        query: str,
        image_urls: list[str],
        account: Account,
    ):
        app = self.get_app(session, app_id, account)
        config = self._config_to_dict(self.get_or_create_draft_config(session, app))
        yield from self.run_app_agent(
            session=session,
            task_id=task_id,
            config=config,
            query=query,
            image_urls=image_urls,
            account=account,
        )

    def run_app_agent(
        self,
        session: Session,
        *,
        task_id: UUID,
        config: dict[str, Any],
        query: str,
        image_urls: list[str],
        account: Account,
        conversation_id: UUID | None = None,
        conversation_summary: str = "",
    ):
        start_at = time.perf_counter()
        long_term_memory = conversation_summary if config["long_term_memory"].get("enable", False) else ""
        if long_term_memory:
            yield AgentThought(
                id=uuid4(),
                task_id=task_id,
                event=QueueEvent.LONG_TERM_MEMORY_RECALL,
                observation=long_term_memory,
            )

        dataset_context, dataset_hits = self._retrieve_dataset_context(session, config, query, account)
        if dataset_hits:
            yield AgentThought(
                id=uuid4(),
                task_id=task_id,
                event=QueueEvent.DATASET_RETRIEVAL,
                observation=json.dumps(dataset_hits, ensure_ascii=False, default=str),
                tool="dataset_retrieval",
                tool_input={"query": query},
            )

        if AgentQueueManager.is_stopped(task_id):
            yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.STOP)
            return

        input_review_response = self._input_review_response(query, config["review_config"])
        try:
            if input_review_response is not None:
                yield from self._yield_answer(
                    task_id=task_id,
                    query=query,
                    answer=input_review_response,
                    start_at=start_at,
                    messages=[{"role": "user", "content": query}],
                )
                return
            else:
                llm = LanguageModelService().load_language_model(config.get("model_config", {}), session, account)
                model_image_urls = (
                    self._prepare_image_urls_for_model(session, account, image_urls)
                    if image_urls and ModelFeature.IMAGE_INPUT in llm.features
                    else image_urls
                )
                history = (
                    TokenBufferMemory(session, conversation_id).get_history_messages(config["dialog_round"])
                    if conversation_id
                    else []
                )
                capability_context = ""
                capabilities = self._build_runtime_capabilities(session, config, account)
                if capabilities and not self._supports_iterative_capabilities(llm):
                    capability_context, capability_thoughts = self._execute_configured_capabilities(
                        session,
                        task_id,
                        config,
                        query,
                        account,
                    )
                    yield from capability_thoughts

                if AgentQueueManager.is_stopped(task_id):
                    yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.STOP)
                    return

                system_prompt = self._build_system_prompt(
                    preset_prompt=config["preset_prompt"],
                    long_term_memory=long_term_memory,
                    dataset_context=dataset_context,
                    capability_context=capability_context,
                )
                if capabilities and self._supports_iterative_capabilities(llm):
                    yield from self._run_iterative_agent(
                        session=session,
                        task_id=task_id,
                        query=query,
                        image_urls=model_image_urls,
                        history=history,
                        system_prompt=system_prompt,
                        llm=llm,
                        review_config=config["review_config"],
                        capabilities=capabilities,
                        account=account,
                        start_at=start_at,
                    )
                    return

                answer = ChatCompletionRuntime().complete(
                    model=llm,
                    query=query,
                    image_urls=model_image_urls,
                    history=history,
                    system_prompt=system_prompt,
                )
                yield from self._yield_answer(
                    task_id=task_id,
                    query=query,
                    answer=self._apply_output_review(answer, config["review_config"]),
                    start_at=start_at,
                    messages=[{"role": "user", "content": query}],
                )
                return
        except Exception as exc:
            yield AgentThought(
                id=uuid4(),
                task_id=task_id,
                event=QueueEvent.ERROR,
                observation=str(exc),
                latency=time.perf_counter() - start_at,
            )
            return

    def _run_iterative_agent(
        self,
        session: Session,
        task_id: UUID,
        query: str,
        image_urls: list[str],
        history: list[dict[str, Any]],
        system_prompt: str,
        llm: BaseLanguageModel,
        review_config: dict[str, Any],
        capabilities: list[RuntimeCapability],
        account: Account,
        start_at: float,
    ):
        runtime = ChatCompletionRuntime()
        capability_map = {capability.name: capability for capability in capabilities}
        messages = self._initial_iterative_messages(llm, system_prompt, history, query, image_urls, capabilities)
        tool_schemas = self._capabilities_to_openai_tools(capabilities)
        use_provider_tool_call = ModelFeature.TOOL_CALL in llm.features

        for iteration_count in range(1, self._max_iteration_count() + 1):
            if AgentQueueManager.is_stopped(task_id):
                yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.STOP)
                return

            response = runtime.create_response(
                model=llm,
                messages=messages,
                tools=tool_schemas if use_provider_tool_call else None,
            )
            tool_calls = response.tool_calls if use_provider_tool_call else []
            use_provider_tool_messages = bool(tool_calls)
            if not tool_calls:
                tool_calls = self._parse_react_tool_calls(response.content)
                use_provider_tool_messages = False
            if not tool_calls:
                yield from self._yield_answer(
                    task_id=task_id,
                    query=query,
                    answer=self._apply_output_review(response.content, review_config),
                    start_at=start_at,
                    messages=messages,
                    total_token_count=self._result_token_count(response.usage, query, response.content),
                )
                return

            yield AgentThought(
                id=uuid4(),
                task_id=task_id,
                event=QueueEvent.AGENT_THOUGHT,
                thought=json.dumps([tool_call.__dict__ for tool_call in tool_calls], ensure_ascii=False),
                message=messages,
                total_token_count=self._result_token_count(response.usage, query, response.content),
                latency=time.perf_counter() - start_at,
            )

            if use_provider_tool_messages:
                messages.append(response.message)
            else:
                messages.append({"role": "assistant", "content": response.content})

            for tool_call in tool_calls:
                if tool_call.parse_error:
                    observation = tool_call.parse_error
                    event = QueueEvent.AGENT_ACTION
                else:
                    capability = capability_map.get(tool_call.name)
                    if capability is None:
                        observation = f"Tool does not exist: {tool_call.name}"
                        event = QueueEvent.AGENT_ACTION
                    else:
                        event = self._capability_event(capability)
                        observation = self._invoke_runtime_capability(
                            session,
                            capability,
                            tool_call.args,
                            account,
                            query,
                        )

                yield AgentThought(
                    id=uuid4(),
                    task_id=task_id,
                    event=event,
                    observation=observation,
                    tool=tool_call.name,
                    tool_input=tool_call.args,
                    latency=time.perf_counter() - start_at,
                )
                self._append_tool_observation(messages, tool_call, observation, use_provider_tool_messages)

            if iteration_count == self._max_iteration_count():
                yield from self._yield_answer(
                    task_id=task_id,
                    query=query,
                    answer=MAX_AGENT_ITERATION_RESPONSE,
                    start_at=start_at,
                    messages=messages,
                )
                return

    @staticmethod
    def _supports_iterative_capabilities(llm: BaseLanguageModel) -> bool:
        return ModelFeature.TOOL_CALL in llm.features or ModelFeature.AGENT_THOUGHT in llm.features

    def _prepare_image_urls_for_model(self, session: Session, account: Account, image_urls: list[str]) -> list[str]:
        return [self._prepare_image_url_for_model(session, account, image_url) for image_url in image_urls]

    def _prepare_image_url_for_model(self, session: Session, account: Account, image_url: str) -> str:
        if not image_url or image_url.startswith("data:"):
            return image_url
        upload_path = self._uploaded_file_path_from_url(image_url)
        if not upload_path:
            return image_url

        file = (
            session.query(File)
            .filter(File.account_id == account.id, File.file_path == upload_path, File.status == "available")
            .one_or_none()
        )
        if file is None:
            raise NotFoundException("Image file does not exist")
        if not (file.mime_type or "").startswith("image/"):
            raise FailException("Image URL does not reference an image file")

        content = self.storage_service.read(session, account.id, file.storage_provider, file.file_path)
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{file.mime_type};base64,{encoded}"

    @staticmethod
    def _uploaded_file_path_from_url(image_url: str) -> str:
        parsed = urlparse(image_url)
        path = parsed.path if parsed.scheme else image_url
        for marker in ("/api/upload-files/", "/upload-files/"):
            index = path.find(marker)
            if index >= 0:
                return unquote(path[index + len(marker) :]).lstrip("/")
        return ""

    def _initial_iterative_messages(
        self,
        llm: BaseLanguageModel,
        system_prompt: str,
        history: list[dict[str, Any]],
        query: str,
        image_urls: list[str],
        capabilities: list[RuntimeCapability],
    ) -> list[dict[str, Any]]:
        if ModelFeature.TOOL_CALL in llm.features:
            return ChatCompletionRuntime._build_messages(system_prompt, history, query, image_urls)

        react_prompt = "\n\n".join(
            [
                system_prompt,
                "You may call a tool by returning only a fenced JSON block.",
                'Tool call format: ```json\n{"name": "tool_name", "args": {"param": "value"}}\n```',
                "When you have enough information, answer normally without a JSON block.",
                f"Available tools:\n{self._render_capability_descriptions(capabilities)}",
            ]
        )
        return ChatCompletionRuntime._build_messages(react_prompt, history, query, image_urls)

    @classmethod
    def _parse_react_tool_calls(cls, content: str) -> list[ChatToolCall]:
        text = content.strip()
        payload_text = cls._extract_react_json(text)
        if not payload_text:
            return []
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return []
        return cls._react_payload_to_tool_calls(payload)

    @classmethod
    def _extract_react_json(cls, text: str) -> str:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match is not None:
            return match.group(1).strip()
        return text if text.startswith(("{", "[")) else ""

    @classmethod
    def _react_payload_to_tool_calls(cls, payload: Any) -> list[ChatToolCall]:
        if isinstance(payload, dict) and isinstance(payload.get("tool_calls"), list):
            payloads = payload["tool_calls"]
        elif isinstance(payload, list):
            payloads = payload
        else:
            payloads = [payload]

        tool_calls: list[ChatToolCall] = []
        for item in payloads:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("tool") or item.get("action") or "")
            if not name:
                continue
            raw_args = item.get("args", item.get("arguments", item.get("action_input", {})))
            args, parse_error = ChatCompletionRuntime._parse_tool_args_with_error(raw_args)
            tool_calls.append(
                ChatToolCall(
                    id=str(item.get("id") or uuid4()),
                    name=name,
                    args=args,
                    parse_error=parse_error,
                )
            )
        return tool_calls

    @staticmethod
    def _append_tool_observation(
        messages: list[dict[str, Any]],
        tool_call: ChatToolCall,
        observation: str,
        use_provider_tool_call: bool,
    ) -> None:
        if use_provider_tool_call:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": observation,
                }
            )
            return

        messages.append(
            {
                "role": "user",
                "content": f"Tool observation for {tool_call.name}:\n{observation}\nContinue the task.",
            }
        )

    def _yield_answer(
        self,
        task_id: UUID,
        query: str,
        answer: str,
        start_at: float,
        messages: list[dict[str, Any]],
        total_token_count: int | None = None,
    ):
        token_count = total_token_count or self._estimate_tokens(query) + self._estimate_tokens(answer)
        event_id = uuid4()
        for chunk in self._split_answer(answer):
            if AgentQueueManager.is_stopped(task_id):
                yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.STOP)
                return
            yield AgentThought(
                id=event_id,
                task_id=task_id,
                event=QueueEvent.AGENT_MESSAGE,
                thought=chunk,
                message=messages,
                answer=chunk,
                total_token_count=token_count,
                latency=time.perf_counter() - start_at,
            )

        yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.AGENT_END)

    @staticmethod
    def _max_iteration_count() -> int:
        return 5

    def _build_runtime_capabilities(
        self,
        session: Session,
        config: dict[str, Any],
        account: Account,
    ) -> list[RuntimeCapability]:
        capabilities: list[RuntimeCapability] = []
        seen_names: set[str] = set()

        for capability_config in config.get("runtime_capabilities", []) or []:
            capability = self._runtime_capability_config_to_capability(capability_config)
            if capability and capability.name not in seen_names:
                capabilities.append(capability)
                seen_names.add(capability.name)

        for tool_config in config.get("tools", []) or []:
            capability = self._tool_config_to_capability(session, tool_config, account)
            if capability and capability.name not in seen_names:
                capabilities.append(capability)
                seen_names.add(capability.name)

        dataset_descriptor = self.capability_adapter.dataset_collection_to_descriptor(
            config.get("datasets", []) or [],
            config.get("retrieval_config") if isinstance(config.get("retrieval_config"), dict) else {},
            config,
        )
        if dataset_descriptor:
            name = self._safe_function_name(dataset_descriptor.name)
            capabilities.append(
                RuntimeCapability(
                    name=name,
                    description=dataset_descriptor.description,
                    parameters=dataset_descriptor.input_schema,
                    kind=dataset_descriptor.kind,
                    config=dataset_descriptor.config,
                )
            )
            seen_names.add(name)

        for workflow_id in self._parse_uuid_list(config.get("workflows", []) or []):
            workflow = session.get(Workflow, workflow_id)
            if workflow is None:
                continue
            descriptor = self.capability_adapter.workflow_to_descriptor(workflow, account)
            if descriptor is None:
                continue
            name = self._safe_function_name(descriptor.name)
            if name in seen_names:
                continue
            capabilities.append(
                RuntimeCapability(
                    name=name,
                    description=descriptor.description,
                    parameters=descriptor.input_schema,
                    kind=descriptor.kind,
                    config=descriptor.config,
                )
            )
            seen_names.add(name)

        return capabilities

    def _tool_config_to_capability(
        self,
        session: Session,
        tool_config: dict[str, Any],
        account: Account,
    ) -> RuntimeCapability | None:
        if not isinstance(tool_config, dict):
            return None

        descriptor = self.capability_adapter.tool_config_to_descriptor(session, tool_config, account)
        if descriptor is None:
            return None
        return RuntimeCapability(
            name=self._safe_function_name(descriptor.name),
            description=descriptor.description,
            parameters=descriptor.input_schema,
            kind=descriptor.kind,
            config=descriptor.config,
        )

    def _invoke_runtime_capability(
        self,
        session: Session,
        capability: RuntimeCapability,
        tool_input: dict[str, Any],
        account: Account,
        query: str,
    ) -> str:
        try:
            if capability.kind == "tool":
                return self._execute_configured_tool(session, capability.config["tool_config"], tool_input, account)
            if capability.kind in {"dataset", "knowledge_base"}:
                app_config = capability.config["app_config"]
                dataset_query = str(tool_input.get("query") or query)
                context, hits = self._retrieve_dataset_context(session, app_config, dataset_query, account)
                return json.dumps(hits, ensure_ascii=False, default=str) if hits else context
            if capability.kind == "workflow":
                workflow_id = UUID(str(capability.config["workflow_id"]))
                workflow = session.get(Workflow, workflow_id)
                if workflow is None:
                    raise NotFoundException("Workflow does not exist")
                return self._execute_workflow_capability(session, workflow, tool_input, account)
            if capability.kind == "create_app":
                app = self.auto_create_app(
                    session,
                    str(tool_input.get("name") or "").strip(),
                    str(tool_input.get("description") or "").strip(),
                    account.id,
                )
                return json.dumps(
                    {"id": str(app.id), "name": app.name, "description": app.description},
                    ensure_ascii=False,
                )
        except Exception as exc:
            return f"{capability.kind.title()} execution failed: {exc}"
        return f"Unsupported capability type: {capability.kind}"

    @staticmethod
    def _capability_event(capability: RuntimeCapability) -> QueueEvent:
        if capability.kind in {"dataset", "knowledge_base"}:
            return QueueEvent.DATASET_RETRIEVAL
        return QueueEvent.AGENT_ACTION

    @staticmethod
    def _capabilities_to_openai_tools(capabilities: list[RuntimeCapability]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": capability.name,
                    "description": capability.description or capability.name,
                    "parameters": capability.parameters,
                },
            }
            for capability in capabilities
        ]

    @classmethod
    def _render_capability_descriptions(cls, capabilities: list[RuntimeCapability]) -> str:
        lines = []
        for capability in capabilities:
            lines.append(
                f"- {capability.name}: {capability.description or capability.name}, "
                f"args: {json.dumps(capability.parameters, ensure_ascii=False)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _runtime_capability_config_to_capability(capability_config: dict[str, Any]) -> RuntimeCapability | None:
        if not isinstance(capability_config, dict):
            return None
        if capability_config.get("type") != "create_app":
            return None
        return RuntimeCapability(
            name="create_app",
            description="Create a draft Agent app for the current user.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Agent app name, no more than 40 characters.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the Agent app to create.",
                    },
                },
                "required": ["name", "description"],
            },
            kind="create_app",
            config={},
        )

    def _builtin_tool_schema(self, tool_entity) -> dict[str, Any]:
        properties = {}
        required = []
        for param in get_tool_params(tool_entity):
            properties[param.name] = {
                "type": self._json_schema_type(param.type),
                "description": param.label,
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.required:
                required.append(param.name)
        return {"type": "object", "properties": properties, "required": required}

    def _api_tool_schema(self, parameters: list[dict[str, Any]]) -> dict[str, Any]:
        properties = {}
        required = []
        for parameter in parameters or []:
            name = str(parameter.get("name") or "")
            if not name:
                continue
            properties[name] = {
                "type": self._json_schema_type(parameter.get("type")),
                "description": str(parameter.get("description") or ""),
            }
            if parameter.get("required", True):
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    def _workflow_input_schema(self, graph: dict[str, Any]) -> dict[str, Any]:
        start_node = next((node for node in graph.get("nodes", []) if node.get("node_type") == "start"), {})
        properties = {}
        required = []
        for variable in start_node.get("inputs") if isinstance(start_node.get("inputs"), list) else []:
            name = str(variable.get("name") or "")
            if not name:
                continue
            properties[name] = {
                "type": self._json_schema_type(variable.get("type")),
                "description": str(variable.get("label") or variable.get("description") or name),
            }
            if variable.get("required", True):
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _json_schema_type(value: Any) -> str:
        type_name = str(value or "string").lower()
        if type_name in {"int", "integer"}:
            return "integer"
        if type_name in {"float", "number"}:
            return "number"
        if type_name in {"bool", "boolean"}:
            return "boolean"
        if type_name == "array":
            return "array"
        if type_name == "object":
            return "object"
        return "string"

    @staticmethod
    def _safe_function_name(value: str) -> str:
        name = re.sub(r"[^A-Za-z0-9_-]", "_", value.strip())
        return (name or "tool")[:64]

    @classmethod
    def _result_token_count(cls, usage: dict[str, Any], query: str, answer: str) -> int:
        if usage.get("total_tokens") is not None:
            return int(usage["total_tokens"])
        return cls._estimate_tokens(query) + cls._estimate_tokens(answer)

    def _retrieve_dataset_context(
        self,
        session: Session,
        config: dict[str, Any],
        query: str,
        account: Account,
    ) -> tuple[str, list[dict]]:
        dataset_ids = []
        for dataset_id in config["datasets"]:
            try:
                dataset_ids.append(UUID(str(dataset_id)))
            except ValueError:
                continue
        if not dataset_ids:
            return "", []

        retrieval_config = config["retrieval_config"]
        hits = []
        dataset_service = DatasetService()
        per_dataset_k = max(1, int(retrieval_config.get("k", 4) or 4))
        for dataset_id in dataset_ids:
            hits.extend(
                dataset_service.hit(
                    session=session,
                    dataset_id=dataset_id,
                    query=query,
                    retrieval_strategy=str(retrieval_config.get("retrieval_strategy", "semantic")),
                    k=per_dataset_k,
                    score=float(retrieval_config.get("score", 0.0) or 0.0),
                    account=account,
                )
            )
        context = "\n\n".join([f"[{idx + 1}] {hit['content']}" for idx, hit in enumerate(hits)])
        return context, hits

    def _execute_configured_capabilities(
        self,
        session: Session,
        task_id: UUID,
        config: dict[str, Any],
        query: str,
        account: Account,
    ) -> tuple[str, list[AgentThought]]:
        observations: list[str] = []
        thoughts: list[AgentThought] = []

        for tool_config in config.get("tools", []) or []:
            if not isinstance(tool_config, dict):
                continue
            tool_name = self._tool_config_name(tool_config)
            tool_input = self._default_tool_input(tool_config, query)
            start_at = time.perf_counter()
            try:
                observation = self._execute_configured_tool(session, tool_config, tool_input, account)
            except Exception as exc:
                observation = f"Tool execution failed: {exc}"

            observations.append(f"{tool_name or 'tool'}: {observation}")
            thoughts.append(
                AgentThought(
                    id=uuid4(),
                    task_id=task_id,
                    event=QueueEvent.AGENT_ACTION,
                    observation=str(observation),
                    tool=tool_name,
                    tool_input=tool_input,
                    latency=time.perf_counter() - start_at,
                )
            )

        for workflow_id in self._parse_uuid_list(config.get("workflows", []) or []):
            start_at = time.perf_counter()
            workflow = session.get(Workflow, workflow_id)
            if workflow is None or workflow.account_id != account.id or workflow.status != "published":
                continue
            workflow_input = self._default_workflow_input(workflow.graph or {}, query)
            try:
                observation = self._execute_workflow_capability(session, workflow, workflow_input, account)
            except Exception as exc:
                observation = f"Workflow execution failed: {exc}"

            observations.append(f"{workflow.tool_call_name}: {observation}")
            thoughts.append(
                AgentThought(
                    id=uuid4(),
                    task_id=task_id,
                    event=QueueEvent.AGENT_ACTION,
                    observation=str(observation),
                    tool=workflow.tool_call_name,
                    tool_input=workflow_input,
                    latency=time.perf_counter() - start_at,
                )
            )

        return "\n\n".join(observations), thoughts

    def _execute_configured_tool(
        self,
        session: Session,
        tool_config: dict[str, Any],
        tool_input: dict[str, Any],
        account: Account,
    ) -> str:
        tool_type = str(tool_config.get("type") or "")
        provider_id = str(tool_config.get("provider_id") or tool_config.get("provider", {}).get("id") or "")
        tool_id = self._tool_config_name(tool_config)

        if tool_type == "builtin_tool":
            tool = BuiltinProviderManager().get_tool(provider_id, tool_id)
            if tool is None:
                raise NotFoundException("Builtin tool does not exist")
            return str(tool.invoke(tool_input))

        if tool_type == "api_tool":
            provider_uuid = self._parse_uuid(provider_id)
            if provider_uuid is None:
                raise NotFoundException("API tool provider does not exist")
            api_tool = (
                session.query(ApiTool)
                .filter(
                    ApiTool.provider_id == provider_uuid,
                    ApiTool.name == tool_id,
                    ApiTool.account_id == account.id,
                )
                .one_or_none()
            )
            if api_tool is None:
                raise NotFoundException("API tool does not exist")
            return str(
                ApiProviderManager()
                .get_tool(
                    ToolEntity(
                        id=str(api_tool.id),
                        name=api_tool.name,
                        url=api_tool.url,
                        method=api_tool.method,
                        description=api_tool.description,
                        headers=api_tool.provider.headers,
                        parameters=api_tool.parameters,
                    )
                )
                .invoke(tool_input)
            )

        raise FailException("Unsupported tool type")

    def _execute_workflow_capability(
        self,
        session: Session,
        workflow: Workflow,
        inputs: dict[str, Any],
        account: Account,
    ) -> str:
        workflow_service = WorkflowService()
        graph = workflow_service.validate_publish_graph(workflow.graph or {})
        node_results: list[dict[str, Any]] = []
        for node in workflow_service._ordered_nodes(graph):
            result = workflow_service._execute_node(session, node, node_results, inputs, account)
            node_results.append(result)
            if result["status"] != "succeeded":
                return result["error"]
        if node_results:
            return json.dumps(node_results[-1].get("outputs", {}), ensure_ascii=False, default=str)
        return "{}"

    @staticmethod
    def _default_tool_input(tool_config: dict[str, Any], query: str) -> dict[str, Any]:
        params = tool_config.get("params") or tool_config.get("tool", {}).get("params") or {}
        if not isinstance(params, dict):
            params = {}
        tool_id = AppService._tool_config_name(tool_config)
        if tool_id in {"google_serper", "duckduckgo_search", "wikipedia_search", "dalle3"}:
            params.setdefault("query", query)
        elif tool_id == "gaode_weather":
            params.setdefault("city", query)
        return params

    @staticmethod
    def _default_workflow_input(graph: dict[str, Any], query: str) -> dict[str, Any]:
        start_node = next(
            (node for node in graph.get("nodes", []) if node.get("node_type") == "start"),
            {},
        )
        inputs = start_node.get("inputs") if isinstance(start_node.get("inputs"), list) else []
        return {
            str(variable.get("name")): query
            for variable in inputs
            if isinstance(variable, dict) and variable.get("name")
        }

    @classmethod
    def _parse_uuid_list(cls, values: list[Any]) -> list[UUID]:
        return [parsed for value in values if (parsed := cls._parse_uuid(value)) is not None]

    @staticmethod
    def _parse_uuid(value: Any) -> UUID | None:
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_system_prompt(
        preset_prompt: str,
        long_term_memory: str,
        dataset_context: str,
        capability_context: str = "",
    ) -> str:
        sections = [
            "You are an application agent. Answer the user based on the app configuration.",
        ]
        if preset_prompt:
            sections.append(f"Preset prompt:\n{preset_prompt}")
        if long_term_memory:
            sections.append(f"Long term memory:\n{long_term_memory}")
        if dataset_context:
            sections.append(f"Dataset context:\n{dataset_context}")
        if capability_context:
            sections.append(f"Tool and workflow context:\n{capability_context}")
        return "\n\n".join(sections)

    @staticmethod
    def _input_review_response(query: str, review_config: dict[str, Any]) -> str | None:
        if not review_config.get("enable") or not review_config.get("inputs_config", {}).get("enable"):
            return None
        keywords = review_config.get("keywords") or []
        if any(str(keyword) and str(keyword) in query for keyword in keywords):
            return str(review_config.get("inputs_config", {}).get("preset_response") or "")
        return None

    @staticmethod
    def _apply_output_review(answer: str, review_config: dict[str, Any]) -> str:
        if not review_config.get("enable") or not review_config.get("outputs_config", {}).get("enable"):
            return answer
        for keyword in review_config.get("keywords") or []:
            if keyword:
                answer = answer.replace(str(keyword), "**")
        return answer

    @staticmethod
    def _split_answer(answer: str, chunk_size: int = 120):
        if not answer:
            yield ""
            return
        for index in range(0, len(answer), chunk_size):
            yield answer[index : index + chunk_size]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    @staticmethod
    def _format_agent_sse(thought: AgentThought, conversation_id: UUID, message_id: UUID) -> str:
        data = {
            **thought.model_dump(
                mode="json",
                include={
                    "event",
                    "thought",
                    "observation",
                    "tool",
                    "tool_input",
                    "answer",
                    "total_token_count",
                    "total_price",
                    "latency",
                },
            ),
            "id": str(thought.id),
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "task_id": str(thought.task_id),
        }
        return f"event: {thought.event.value}\ndata:{json.dumps(data, ensure_ascii=False)}\n\n"

    def _save_agent_result(
        self,
        session: Session,
        account: Account,
        app: App,
        conversation: Conversation,
        message: Message,
        agent_thoughts: list[AgentThought],
    ) -> None:
        non_ping_thoughts = [thought for thought in agent_thoughts if thought.event != QueueEvent.PING]
        answer = "".join(thought.answer for thought in non_ping_thoughts if thought.event == QueueEvent.AGENT_MESSAGE)
        status = MessageStatus.NORMAL.value
        error = ""
        if any(thought.event == QueueEvent.STOP for thought in non_ping_thoughts):
            status = MessageStatus.STOP.value
        if error_thought := next((thought for thought in non_ping_thoughts if thought.event == QueueEvent.ERROR), None):
            status = MessageStatus.ERROR.value
            error = error_thought.observation

        total_token_count = max((thought.total_token_count for thought in non_ping_thoughts), default=0)
        latency = max((thought.latency for thought in non_ping_thoughts), default=0.0)
        self.update(
            session,
            message,
            answer=answer,
            status=status,
            error=error,
            total_token_count=total_token_count,
            latency=latency,
        )

        for position, thought in enumerate(non_ping_thoughts, start=1):
            self.create(
                session,
                MessageAgentThought,
                app_id=app.id,
                conversation_id=conversation.id,
                message_id=message.id,
                invoke_from=InvokeFrom.DEBUGGER.value,
                created_by=account.id,
                position=position,
                event=thought.event.value,
                thought=thought.thought,
                observation=thought.observation,
                tool=thought.tool,
                tool_input=thought.tool_input,
                message=thought.message,
                message_token_count=thought.message_token_count,
                message_unit_price=thought.message_unit_price,
                message_price_unit=thought.message_price_unit,
                answer=thought.answer,
                answer_token_count=thought.answer_token_count,
                answer_unit_price=thought.answer_unit_price,
                answer_price_unit=thought.answer_price_unit,
                total_token_count=thought.total_token_count,
                total_price=thought.total_price,
                latency=thought.latency,
            )

    @classmethod
    def _create_config_version(
        cls,
        session: Session,
        app_id: UUID,
        version: int,
        config_type: str,
        config: dict[str, Any],
    ) -> AppConfigVersion:
        config = cls._normalize_config(config)
        app_config_version = AppConfigVersion(
            app_id=app_id,
            version=version,
            config_type=config_type,
            **config,
        )
        session.add(app_config_version)
        session.flush()
        session.refresh(app_config_version)
        return app_config_version

    def _config_to_response(self, session: Session, config) -> dict[str, Any]:
        return {
            "id": str(config.id),
            **self._config_to_dict(config),
            "tools": self._tool_metadata(session, config.tools or []),
            "workflows": self._workflow_metadata(session, config.workflows or []),
            "datasets": self._dataset_metadata(session, getattr(config, "datasets", []) or []),
            "updated_at": int(config.updated_at.timestamp()) if config.updated_at else 0,
            "created_at": int(config.created_at.timestamp()) if config.created_at else 0,
        }

    @staticmethod
    def _config_to_dict(config) -> dict[str, Any]:
        return {
            "model_config": AppService._normalize_model_config(
                config.model_config or deepcopy(DEFAULT_APP_CONFIG["model_config"])
            ),
            "dialog_round": config.dialog_round,
            "preset_prompt": config.preset_prompt or "",
            "tools": config.tools or [],
            "workflows": config.workflows or [],
            "datasets": getattr(config, "datasets", []) or [],
            "retrieval_config": config.retrieval_config or deepcopy(DEFAULT_APP_CONFIG["retrieval_config"]),
            "long_term_memory": config.long_term_memory or deepcopy(DEFAULT_APP_CONFIG["long_term_memory"]),
            "opening_statement": config.opening_statement or "",
            "opening_questions": config.opening_questions or [],
            "speech_to_text": config.speech_to_text or deepcopy(DEFAULT_APP_CONFIG["speech_to_text"]),
            "text_to_speech": config.text_to_speech or deepcopy(DEFAULT_APP_CONFIG["text_to_speech"]),
            "suggested_after_answer": config.suggested_after_answer
            or deepcopy(DEFAULT_APP_CONFIG["suggested_after_answer"]),
            "review_config": config.review_config or deepcopy(DEFAULT_APP_CONFIG["review_config"]),
        }

    def _validate_config(self, session: Session, data: dict[str, Any], account: Account) -> dict[str, Any]:
        config = self._normalize_config({**deepcopy(DEFAULT_APP_CONFIG), **(data or {})})
        if not isinstance(config["dialog_round"], int) or not (0 <= config["dialog_round"] <= 100):
            raise ValidateErrorException("dialog_round must be between 0 and 100")
        if len(config["tools"]) > 5 or len(config["workflows"]) > 5 or len(config["datasets"]) > 5:
            raise ValidateErrorException("tools, workflows and datasets can contain at most 5 items")
        config["tools"] = self._valid_tools(session, config["tools"], account)
        config["workflows"] = self._valid_workflow_ids(session, config["workflows"], account)
        config["datasets"] = self._valid_dataset_ids(session, config["datasets"], account)
        return config

    @staticmethod
    def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(DEFAULT_APP_CONFIG)
        normalized.update(config or {})
        normalized["model_config"] = AppService._normalize_model_config(normalized.get("model_config"))
        normalized["tools"] = normalized["tools"] if isinstance(normalized["tools"], list) else []
        normalized["workflows"] = [str(item) for item in normalized["workflows"] or []]
        normalized["datasets"] = [str(item) for item in normalized["datasets"] or []]
        return normalized

    @staticmethod
    def _normalize_model_config(model_config: dict[str, Any] | None) -> dict[str, Any]:
        default_model_config = deepcopy(DEFAULT_APP_CONFIG["model_config"])
        if not isinstance(model_config, dict):
            return default_model_config

        normalized = dict(model_config)
        normalized["provider"] = str(normalized.get("provider") or default_model_config["provider"])
        normalized["model"] = str(normalized.get("model") or default_model_config["model"])
        parameters = normalized.get("parameters") if isinstance(normalized.get("parameters"), dict) else {}
        normalized["parameters"] = dict(parameters)

        top_p = normalized["parameters"].get("top_p")
        if top_p is not None:
            try:
                top_p_value = float(top_p)
            except (TypeError, ValueError):
                top_p_value = 0
            if not (0 < top_p_value <= 1):
                normalized["parameters"]["top_p"] = default_model_config["parameters"]["top_p"]
            elif top_p_value != top_p:
                normalized["parameters"]["top_p"] = top_p_value
        return normalized

    @staticmethod
    def _generate_random_string(length: int) -> str:
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    @staticmethod
    def _auto_created_app_prompt(name: str, description: str) -> str:
        return (
            f"You are {name}. Help users with the following goal:\n"
            f"{description}\n\n"
            "Answer clearly, ask for missing context when needed, and keep responses practical."
        )

    def _valid_workflow_ids(self, session: Session, workflow_ids: list[str], account: Account) -> list[str]:
        workflows = (
            session.query(Workflow)
            .filter(Workflow.id.in_(workflow_ids), Workflow.account_id == account.id, Workflow.status == "published")
            .all()
        )
        valid_ids = {str(workflow.id) for workflow in workflows}
        return [workflow_id for workflow_id in workflow_ids if workflow_id in valid_ids]

    def _valid_dataset_ids(self, session: Session, dataset_ids: list[str], account: Account) -> list[str]:
        datasets = session.query(Dataset).filter(Dataset.id.in_(dataset_ids), Dataset.account_id == account.id).all()
        valid_ids = {str(dataset.id) for dataset in datasets}
        return [dataset_id for dataset_id in dataset_ids if dataset_id in valid_ids]

    def _valid_tools(self, session: Session, tools_config: list[dict], account: Account) -> list[dict]:
        valid_tools = []
        for tool_config in tools_config:
            normalized = self._normalize_tool_config(tool_config)
            tool_type = normalized.get("type")
            provider_id = normalized.get("provider_id")
            tool_id = normalized.get("tool_id")
            if tool_type == "builtin_tool":
                provider = BuiltinProviderManager().get_provider(provider_id)
                if provider is None:
                    continue
                tool_entity = provider.get_tool_entity(tool_id)
                if tool_entity is None:
                    continue
                normalized["params"] = self._valid_builtin_tool_params(tool_entity, normalized.get("params", {}))
                valid_tools.append(normalized)
            elif tool_type == "api_tool":
                provider_uuid = self._parse_uuid(provider_id)
                if provider_uuid is None:
                    continue
                exists = (
                    session.query(ApiTool)
                    .filter(
                        ApiTool.provider_id == provider_uuid,
                        ApiTool.name == tool_id,
                        ApiTool.account_id == account.id,
                    )
                    .one_or_none()
                )
                if exists is not None:
                    valid_tools.append(normalized)
        return valid_tools

    def _tool_metadata(self, session: Session, tools_config: list[dict]) -> list[dict]:
        tools = []
        for tool_config in tools_config:
            normalized = self._normalize_tool_config(tool_config)
            if normalized.get("type") == "builtin_tool":
                provider = BuiltinProviderManager().get_provider(normalized["provider_id"])
                if provider is None:
                    continue
                tool_entity = provider.get_tool_entity(normalized["tool_id"])
                if tool_entity is None:
                    continue
                provider_entity = provider.provider_entity
                tools.append(
                    {
                        "type": "builtin_tool",
                        "provider": {
                            "id": provider_entity.name,
                            "name": provider_entity.name,
                            "label": provider_entity.label,
                            "icon": f"/builtin-tools/{provider_entity.name}/icon",
                            "description": provider_entity.description,
                        },
                        "tool": {
                            "id": tool_entity.name,
                            "name": tool_entity.name,
                            "label": tool_entity.label,
                            "description": tool_entity.description,
                            "params": normalized.get("params", {}),
                        },
                    }
                )
            elif normalized.get("type") == "api_tool":
                provider_uuid = self._parse_uuid(normalized["provider_id"])
                if provider_uuid is None:
                    continue
                api_tool = (
                    session.query(ApiTool)
                    .filter(ApiTool.provider_id == provider_uuid, ApiTool.name == normalized["tool_id"])
                    .one_or_none()
                )
                if api_tool is None:
                    continue
                provider = api_tool.provider
                tools.append(
                    {
                        "type": "api_tool",
                        "provider": {
                            "id": str(provider.id),
                            "name": provider.name,
                            "label": provider.name,
                            "icon": provider.icon,
                            "description": provider.description,
                        },
                        "tool": {
                            "id": str(api_tool.id),
                            "name": api_tool.name,
                            "label": api_tool.name,
                            "description": api_tool.description,
                            "params": {},
                        },
                    }
                )
        return tools

    @staticmethod
    def _normalize_tool_config(tool_config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tool_config, dict):
            return {"type": "", "provider_id": "", "tool_id": "", "params": {}}
        return {
            "type": str(tool_config.get("type") or ""),
            "provider_id": str(tool_config.get("provider_id") or tool_config.get("provider", {}).get("id") or ""),
            "tool_id": AppService._tool_config_name(tool_config),
            "params": tool_config.get("params") or tool_config.get("tool", {}).get("params") or {},
        }

    @staticmethod
    def _tool_config_name(tool_config: dict[str, Any]) -> str:
        tool = tool_config.get("tool", {}) if isinstance(tool_config.get("tool"), dict) else {}
        return str(tool_config.get("tool_id") or tool.get("id") or tool.get("name") or "")

    @staticmethod
    def _valid_builtin_tool_params(tool_entity, params: dict[str, Any]) -> dict[str, Any]:
        params = params if isinstance(params, dict) else {}
        param_keys = {param.name for param in tool_entity.params}
        if set(params.keys()) - param_keys:
            return {param.name: param.default for param in tool_entity.params if param.default is not None}
        return params

    def _workflow_metadata(self, session: Session, workflow_ids: list[str]) -> list[dict]:
        workflows = session.query(Workflow).filter(Workflow.id.in_(workflow_ids)).all() if workflow_ids else []
        workflow_map = {str(workflow.id): workflow for workflow in workflows}
        return [
            {
                "id": str(workflow.id),
                "name": workflow.name,
                "icon": workflow.icon,
                "description": workflow.description,
            }
            for workflow_id in workflow_ids
            if (workflow := workflow_map.get(str(workflow_id))) is not None
        ]

    def _dataset_metadata(self, session: Session, dataset_ids: list[str]) -> list[dict]:
        datasets = session.query(Dataset).filter(Dataset.id.in_(dataset_ids)).all() if dataset_ids else []
        dataset_map = {str(dataset.id): dataset for dataset in datasets}
        return [
            {
                "id": str(dataset.id),
                "name": dataset.name,
                "icon": dataset.icon,
                "description": dataset.description,
            }
            for dataset_id in dataset_ids
            if (dataset := dataset_map.get(str(dataset_id))) is not None
        ]
