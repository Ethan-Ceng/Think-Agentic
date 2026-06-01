from typing import Any

from pydantic import BaseModel, Field

from app.core.app import DEFAULT_APP_CONFIG


class BuiltinAppEntity(BaseModel):
    id: str = ""
    category: str = ""
    name: str = ""
    icon: str = ""
    description: str = ""
    language_model_config: dict[str, Any] = Field(
        default_factory=lambda: dict(DEFAULT_APP_CONFIG["model_config"])
    )
    dialog_round: int = DEFAULT_APP_CONFIG["dialog_round"]
    preset_prompt: str = DEFAULT_APP_CONFIG["preset_prompt"]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_config: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APP_CONFIG["retrieval_config"]))
    long_term_memory: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APP_CONFIG["long_term_memory"]))
    opening_statement: str = DEFAULT_APP_CONFIG["opening_statement"]
    opening_questions: list[str] = Field(default_factory=lambda: list(DEFAULT_APP_CONFIG["opening_questions"]))
    speech_to_text: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APP_CONFIG["speech_to_text"]))
    text_to_speech: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APP_CONFIG["text_to_speech"]))
    suggested_after_answer: dict[str, Any] = Field(
        default_factory=lambda: dict(DEFAULT_APP_CONFIG["suggested_after_answer"])
    )
    review_config: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APP_CONFIG["review_config"]))
    created_at: int = 0
