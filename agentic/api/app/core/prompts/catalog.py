from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.core.prompts.en.planner import (
    CREATE_PLAN_PROMPT as EN_CREATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT as EN_PLANNER_SYSTEM_PROMPT,
    UPDATE_PLAN_PROMPT as EN_UPDATE_PLAN_PROMPT,
)
from app.core.prompts.en.react import (
    EXECUTION_PROMPT as EN_EXECUTION_PROMPT,
    GOAL_EXECUTION_PROMPT as EN_GOAL_EXECUTION_PROMPT,
    REACT_SYSTEM_PROMPT as EN_REACT_SYSTEM_PROMPT,
    SUMMARIZE_PROMPT as EN_SUMMARIZE_PROMPT,
)
from app.core.prompts.en.system import SYSTEM_PROMPT as EN_SYSTEM_PROMPT
from app.core.prompts.planner import (
    CREATE_PLAN_PROMPT as ZH_CREATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT as ZH_PLANNER_SYSTEM_PROMPT,
    UPDATE_PLAN_PROMPT as ZH_UPDATE_PLAN_PROMPT,
)
from app.core.prompts.react import (
    EXECUTION_PROMPT as ZH_EXECUTION_PROMPT,
    GOAL_EXECUTION_PROMPT as ZH_GOAL_EXECUTION_PROMPT,
    REACT_SYSTEM_PROMPT as ZH_REACT_SYSTEM_PROMPT,
    SUMMARIZE_PROMPT as ZH_SUMMARIZE_PROMPT,
)
from app.core.prompts.system import SYSTEM_PROMPT as ZH_SYSTEM_PROMPT


class PromptLocale(str, Enum):
    ZH = "zh"
    EN = "en"


@dataclass(frozen=True)
class PlannerPrompts:
    system: str
    create: str
    update: str


@dataclass(frozen=True)
class ReactPrompts:
    system: str
    execution: str
    goal_execution: str
    summarize: str


_ZH_LANGUAGE_MARKERS = ("chinese", "中文", "汉语", "漢語", "华语", "華語")
_EN_LANGUAGE_MARKERS = ("english", "英文", "英语", "英語")
_FIRST_LANGUAGE_CHAR = re.compile(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff]")


def resolve_prompt_locale(language: str | None) -> PromptLocale:
    """Map a Lead working-language label to one of the available prompt packs."""
    normalized = (language or "").strip().lower().replace("_", "-")
    if not normalized:
        return PromptLocale.ZH
    if normalized == "zh" or normalized.startswith("zh-"):
        return PromptLocale.ZH
    if any(marker in normalized for marker in _ZH_LANGUAGE_MARKERS):
        return PromptLocale.ZH
    if normalized == "en" or normalized.startswith("en-"):
        return PromptLocale.EN
    if any(marker in normalized for marker in _EN_LANGUAGE_MARKERS):
        return PromptLocale.EN
    return PromptLocale.EN


def infer_prompt_locale(message: str | None) -> PromptLocale:
    """Choose the Legacy first-turn pack from the first language-bearing character."""
    match = _FIRST_LANGUAGE_CHAR.search(message or "")
    if match is None:
        return PromptLocale.ZH
    return (
        PromptLocale.EN
        if match.group(0).isascii()
        else PromptLocale.ZH
    )


_PLANNER_PROMPTS = {
    PromptLocale.ZH: PlannerPrompts(
        system=ZH_SYSTEM_PROMPT + ZH_PLANNER_SYSTEM_PROMPT,
        create=ZH_CREATE_PLAN_PROMPT,
        update=ZH_UPDATE_PLAN_PROMPT,
    ),
    PromptLocale.EN: PlannerPrompts(
        system=EN_SYSTEM_PROMPT + EN_PLANNER_SYSTEM_PROMPT,
        create=EN_CREATE_PLAN_PROMPT,
        update=EN_UPDATE_PLAN_PROMPT,
    ),
}

_REACT_PROMPTS = {
    PromptLocale.ZH: ReactPrompts(
        system=ZH_SYSTEM_PROMPT + ZH_REACT_SYSTEM_PROMPT,
        execution=ZH_EXECUTION_PROMPT,
        goal_execution=ZH_GOAL_EXECUTION_PROMPT,
        summarize=ZH_SUMMARIZE_PROMPT,
    ),
    PromptLocale.EN: ReactPrompts(
        system=EN_SYSTEM_PROMPT + EN_REACT_SYSTEM_PROMPT,
        execution=EN_EXECUTION_PROMPT,
        goal_execution=EN_GOAL_EXECUTION_PROMPT,
        summarize=EN_SUMMARIZE_PROMPT,
    ),
}


def get_planner_prompts(language: str | PromptLocale | None) -> PlannerPrompts:
    locale = (
        language
        if isinstance(language, PromptLocale)
        else resolve_prompt_locale(language)
    )
    return _PLANNER_PROMPTS[locale]


def get_react_prompts(language: str | PromptLocale | None) -> ReactPrompts:
    locale = (
        language
        if isinstance(language, PromptLocale)
        else resolve_prompt_locale(language)
    )
    return _REACT_PROMPTS[locale]
