import base64
import json
from dataclasses import dataclass, field
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.app import AppStatus
from app.core.config import Settings, get_settings
from app.core.conversation import InvokeFrom
from app.core.exceptions import FailException, NotFoundException
from app.models.account import Account
from app.models.app import App, AppConfig, AppConfigVersion
from app.models.conversation import Conversation, Message
from app.services.app_service import AppService
from app.services.base_service import BaseService


@dataclass
class AudioService(BaseService):
    app_service: AppService = field(default_factory=AppService)
    settings: Settings = field(default_factory=get_settings)

    def audio_to_text(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        api_key = self.settings.openai_api_key
        if not api_key:
            raise FailException("Missing provider credential: OPENAI_API_KEY")

        base_url = self.settings.openai_base_url.rstrip("/")
        files = {"file": (filename or "recording.wav", content, content_type or "application/octet-stream")}
        data = {"model": self.settings.openai_audio_transcription_model}
        headers = {"Authorization": f"Bearer {api_key}"}
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{base_url}/audio/transcriptions", headers=headers, data=data, files=files)
        if response.status_code >= 400:
            raise FailException(f"Audio transcription failed: {response.status_code} {response.text[:500]}")
        return str(response.json().get("text") or "")

    def message_to_audio(self, session: Session, message_id: UUID, account: Account):
        message = session.get(Message, message_id)
        if message is None or message.is_deleted or not message.answer.strip() or message.created_by != account.id:
            raise NotFoundException("Message does not exist")

        conversation = session.get(Conversation, message.conversation_id)
        if conversation is None or conversation.is_deleted:
            raise NotFoundException("Conversation does not exist")

        enable, voice = self._resolve_text_to_speech_config(session, message, conversation, account)
        if not enable:
            raise FailException("Text to speech is not enabled")

        api_key = self.settings.openai_api_key
        if not api_key:
            raise FailException("Missing provider credential: OPENAI_API_KEY")

        base_url = self.settings.openai_base_url.rstrip("/")
        payload = {
            "model": self.settings.openai_tts_model,
            "voice": voice or "echo",
            "response_format": "mp3",
            "input": message.answer.strip(),
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        def generate():
            common_data = {
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "audio": "",
            }
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", f"{base_url}/audio/speech", headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        raise FailException(f"Text to speech failed: {response.status_code}")
                    for chunk in response.iter_bytes(1024):
                        if chunk:
                            data = {**common_data, "audio": base64.b64encode(chunk).decode("utf-8")}
                            yield f"event: tts_message\ndata: {json.dumps(data)}\n\n"
            yield f"event: tts_end\ndata: {json.dumps(common_data)}\n\n"

        return generate()

    def _resolve_text_to_speech_config(
        self,
        session: Session,
        message: Message,
        conversation: Conversation,
        account: Account,
    ) -> tuple[bool, str]:
        if message.invoke_from == InvokeFrom.SERVICE_API.value:
            raise NotFoundException("Service API messages do not support text to speech")

        app = session.get(App, conversation.app_id)
        if app is None:
            raise NotFoundException("App does not exist")
        if message.invoke_from == InvokeFrom.DEBUGGER.value and app.account_id != account.id:
            raise NotFoundException("App does not exist")
        if message.invoke_from == InvokeFrom.WEB_APP.value and app.status != AppStatus.PUBLISHED.value:
            raise NotFoundException("App is not published")

        app_config: AppConfig | AppConfigVersion | None
        if message.invoke_from == InvokeFrom.DEBUGGER.value:
            app_config = session.get(AppConfigVersion, app.draft_app_config_id) if app.draft_app_config_id else None
        else:
            app_config = session.get(AppConfig, app.app_config_id) if app.app_config_id else None
        if app_config is None:
            raise NotFoundException("App config does not exist")

        text_to_speech = app_config.text_to_speech or {}
        return bool(text_to_speech.get("enable", False)), str(text_to_speech.get("voice") or "echo")
