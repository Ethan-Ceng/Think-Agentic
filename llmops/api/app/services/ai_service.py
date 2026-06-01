import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException
from app.core.language_model.chat_runtime import ChatCompletionRuntime
from app.models.account import Account
from app.models.conversation import Message
from app.services.base_service import BaseService
from app.services.language_model_service import LanguageModelService

OPTIMIZE_PROMPT_TEMPLATE = """You are a prompt engineer.
Rewrite the user's prompt so it is clearer, more specific, and easier for an agent to execute.
Return only the optimized prompt."""


@dataclass
class AIService(BaseService):
    def generate_suggested_questions_from_message_id(
        self,
        session: Session,
        message_id: UUID,
        account: Account,
    ) -> list[str]:
        message = session.get(Message, message_id)
        if message is None or message.created_by != account.id:
            raise ForbiddenException("Message does not exist or is not accessible")

        subject = (message.query or "this topic").strip()[:80]
        return [
            f"Can you explain more about {subject}?",
            "What are the next practical steps?",
            "Are there any risks or alternatives I should consider?",
        ]

    def optimize_prompt(self, prompt: str):
        try:
            llm = LanguageModelService().load_default_language_model()
            optimized = ChatCompletionRuntime().complete(
                model=llm,
                query=prompt,
                system_prompt=OPTIMIZE_PROMPT_TEMPLATE,
            )
        except Exception:
            optimized = self._fallback_optimize_prompt(prompt)

        data = {"optimize_prompt": optimized}
        yield f"event: optimize_prompt\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _fallback_optimize_prompt(prompt: str) -> str:
        prompt = prompt.strip()
        return (
            "Role: You are a precise and practical assistant.\n"
            f"Task: {prompt}\n"
            "Requirements: clarify assumptions, provide actionable steps, and keep the answer concise.\n"
            "Output: use structured sections when helpful."
        )
