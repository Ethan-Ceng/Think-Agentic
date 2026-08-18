from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.core.agent.base import BaseAgent
from app.core.entities.lead import (
    LEAD_DECISION_ADAPTER,
    DirectDecision,
    LeadDecision,
    ReactDecision,
)
from app.core.entities.message import Message
from app.core.prompts.lead import LEAD_DECISION_PROMPT, LEAD_SYSTEM_PROMPT


_EXTERNAL_REQUEST_PATTERNS = (
    re.compile(r"https?://|www\.", re.IGNORECASE),
    re.compile(
        r"\b(latest|right now|real[- ]?time|breaking news)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\b(?:please|can you|could you)\s+)"
        r"(?:search|browse|open|download|upload|send|create|modify|delete|run|execute)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:today|now)\b.{0,24}\b(?:weather|price|score|schedule|news|rate)\b"
        r"|\b(?:weather|price|score|schedule|news|rate)\b.{0,24}\b(?:today|now)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(最新|实时|突发新闻)"),
    re.compile(r"(?:今天|现在).{0,12}(?:天气|价格|股价|新闻|赛程|汇率|时间)"),
    re.compile(r"(?:请|帮我|替我|为我).{0,8}(?:搜索|检索|浏览|打开|下载|上传|发送|创建|修改|删除|运行|执行)"),
    re.compile(r"^(?:搜索|检索|浏览|打开|下载|上传|发送|创建|修改|删除|运行|执行)"),
)
_INLINE_TRANSFORM_PATTERN = re.compile(
    r"^\s*(?:please\s+)?(?:translate|rewrite|polish|summarize the following)\b"
    r"|^\s*(?:请)?(?:把|将).{0,16}(?:翻译|改写|润色|总结)",
    re.IGNORECASE,
)


class LeadDecisionPolicy(BaseAgent):
    """Make one structured routing decision without exposing Tool schemas."""

    name = "lead"
    _system_prompt = LEAD_SYSTEM_PROMPT
    _format: Optional[str] = "json_object"
    _tool_choice: Optional[str] = "none"

    def _get_available_tools(self) -> list[dict]:
        return []

    def _capability_catalog(self) -> str:
        catalog = (
            self._tool_registry.list_capability_catalog()
            if self._tool_registry is not None
            else []
        )
        return json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))

    def _known_capabilities(self) -> set[str] | None:
        if self._tool_registry is None:
            return None
        return self._tool_registry.capability_groups()

    @staticmethod
    def _assert_direct_is_safe(message: Message) -> None:
        if message.attachments:
            raise ValueError("Direct 模式不允许读取附件")
        text = message.message or ""
        if _EXTERNAL_REQUEST_PATTERNS[0].search(text):
            raise ValueError("Direct 模式不允许获取外部信息或执行外部动作")
        if _INLINE_TRANSFORM_PATTERN.search(text):
            return
        if any(pattern.search(text) for pattern in _EXTERNAL_REQUEST_PATTERNS[1:]):
            raise ValueError("Direct 模式不允许获取外部信息或执行外部动作")

    def _filter_capabilities(self, values: list[str]) -> list[str]:
        known = self._known_capabilities()
        if known is None:
            return values
        return [value for value in values if value in known]

    def _normalize_decision(
        self,
        parsed: Any,
        message: Message,
    ) -> LeadDecision:
        decision = LEAD_DECISION_ADAPTER.validate_python(parsed)
        if isinstance(decision, DirectDecision):
            self._assert_direct_is_safe(message)
            return decision
        if isinstance(decision, ReactDecision):
            return decision.model_copy(
                update={
                    "capabilities": self._filter_capabilities(decision.capabilities),
                }
            )

        normalized_steps = [
            type(step)(
                id=step.id,
                description=step.description,
                capabilities=self._filter_capabilities(step.capabilities),
            )
            for step in decision.steps
        ]
        normalized_plan = decision.model_copy(update={"steps": normalized_steps})
        if len(normalized_plan.steps) == 1:
            step = normalized_plan.steps[0]
            return ReactDecision(
                title=normalized_plan.title,
                language=normalized_plan.language,
                goal=step.description,
                capabilities=step.capabilities,
            )
        return normalized_plan

    async def decide(self, message: Message) -> LeadDecision:
        self.set_runtime_tool_scope([])
        query = LEAD_DECISION_PROMPT.format(
            message=message.message,
            attachments="\n".join(message.attachments),
            capability_catalog=self._capability_catalog(),
        )
        response = await self._invoke_llm(
            [{"role": "user", "content": query}],
            self._format,
        )
        content = response.get("content")
        if not content:
            raise ValueError("Lead 决策没有返回可解析内容")
        parsed = await self._json_parser.invoke(content)
        return self._normalize_decision(parsed, message)
