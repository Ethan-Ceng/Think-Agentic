"""Manual-first, metadata-only automatic Skill selection."""

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.entities.skill import (
    SelectedSkill,
    SkillSelectionMode,
)
from app.core.llm.base import LLM
from app.core.prompts.skill_selector import build_skill_selector_messages
from app.schemas.skill import (
    SkillCatalogItem,
    SkillSelectionRequest,
    SkillSelectionResult,
    SkillSelectionSkip,
)
from app.services.skill_catalog_service import SkillCatalogService
from app.services.trace_service import elapsed_ms, model_call_timer


MANUAL_LIMIT = 5
AUTOMATIC_LIMIT = 3
COMBINED_LIMIT = 5


class _AutomaticChoice(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=256)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("selection reason cannot be blank")
        return reason


class _AutomaticResponse(BaseModel):
    skills: list[_AutomaticChoice] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SkillSelectionService:
    def __init__(
        self,
        *,
        catalog_service: SkillCatalogService,
        llm_provider: Callable[[str], Awaitable[LLM]],
        trace_service: Any | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        self._llm_provider = llm_provider
        self._trace_service = trace_service

    async def select(
        self, request: SkillSelectionRequest
    ) -> SkillSelectionResult:
        catalog = await self._catalog_service.get_catalog(request.user_id)
        selected: list[SelectedSkill] = []
        skipped: list[SkillSelectionSkip] = []
        selected_keys: set[str] = set()

        for index, ref in enumerate(request.manual_refs):
            if index >= MANUAL_LIMIT:
                skipped.append(
                    self._skip(
                        mode=SkillSelectionMode.MANUAL,
                        code="manual_limit",
                        reason="At most 5 manually selected Skills are allowed.",
                        ref=ref,
                    )
                )
                continue
            item = catalog.resolve(ref)
            if item is None:
                skipped.append(
                    self._skip(
                        mode=SkillSelectionMode.MANUAL,
                        code="unavailable",
                        reason="The selected Skill is disabled or unavailable.",
                        ref=ref,
                    )
                )
                continue
            missing = self._missing_tools(item, request.available_tool_names)
            if missing:
                skipped.append(
                    self._skip(
                        mode=SkillSelectionMode.MANUAL,
                        code="missing_tools",
                        reason=f"Required tools are unavailable: {', '.join(missing)}.",
                        ref=ref,
                    )
                )
                continue
            if item.selector_key in selected_keys:
                continue
            selected.append(self._selected(item, SkillSelectionMode.MANUAL))
            selected_keys.add(item.selector_key)

        remaining = COMBINED_LIMIT - len(selected)
        if remaining <= 0:
            return SkillSelectionResult(selected=selected, skipped=skipped)

        candidates = [
            item
            for item in catalog.automatic_candidates
            if item.selector_key not in selected_keys
            and not self._missing_tools(item, request.available_tool_names)
        ]
        if not candidates:
            return SkillSelectionResult(selected=selected, skipped=skipped)

        model_call_id: str | None = None
        started = model_call_timer()
        messages = build_skill_selector_messages(
            message=request.message,
            attachment_media_types=request.attachment_media_types,
            candidates=candidates,
        )
        response_format = {"type": "json_object"}
        try:
            llm = await self._llm_provider(request.user_id)
            if self._trace_service:
                model_call_id = await self._trace_service.record_model_call_started(
                    agent_name="skill_selector",
                    llm=llm,
                    messages=messages,
                    tools=[],
                    response_format=response_format,
                    tool_choice=None,
                )
            message = await llm.invoke(
                messages=messages,
                tools=[],
                response_format=response_format,
                tool_choice=None,
            )
            if self._trace_service:
                await self._trace_service.record_model_call_finished(
                    model_call_id,
                    message=message,
                    latency_ms=elapsed_ms(started),
                )
        except Exception as exc:
            if self._trace_service and model_call_id:
                await self._trace_service.record_model_call_finished(
                    model_call_id,
                    error=str(exc),
                    latency_ms=elapsed_ms(started),
                )
            skipped.append(
                self._skip(
                    mode=SkillSelectionMode.AUTOMATIC,
                    code="selector_failed",
                    reason="Automatic Skill selection was unavailable; manual selections were kept.",
                )
            )
            return SkillSelectionResult(
                selected=selected,
                skipped=skipped,
                selector_model_call_id=model_call_id,
            )

        try:
            parsed = _AutomaticResponse.model_validate(
                json.loads(message.get("content") or "")
            )
        except (json.JSONDecodeError, TypeError, ValidationError):
            skipped.append(
                self._skip(
                    mode=SkillSelectionMode.AUTOMATIC,
                    code="selector_invalid_response",
                    reason="Automatic Skill selection returned an invalid response.",
                )
            )
            return SkillSelectionResult(
                selected=selected,
                skipped=skipped,
                selector_model_call_id=model_call_id,
            )

        by_key = {item.selector_key: item for item in candidates}
        automatic_count = 0
        for choice in parsed.skills:
            item = by_key.get(choice.key)
            if item is None:
                skipped.append(
                    self._skip(
                        mode=SkillSelectionMode.AUTOMATIC,
                        code="unknown_selector_key",
                        reason="The selector returned a Skill outside the candidate catalog.",
                        requested_key=choice.key,
                    )
                )
                continue
            if item.selector_key in selected_keys:
                continue
            if automatic_count >= min(AUTOMATIC_LIMIT, remaining):
                skipped.append(
                    self._skip(
                        mode=SkillSelectionMode.AUTOMATIC,
                        code="automatic_limit",
                        reason="The automatic Skill selection limit was reached.",
                        ref=item.ref,
                    )
                )
                continue
            selected.append(
                self._selected(
                    item,
                    SkillSelectionMode.AUTOMATIC,
                    confidence=choice.confidence,
                    reason=choice.reason,
                )
            )
            selected_keys.add(item.selector_key)
            automatic_count += 1

        return SkillSelectionResult(
            selected=selected,
            skipped=skipped,
            selector_model_call_id=model_call_id,
        )

    @staticmethod
    def _selected(
        item: SkillCatalogItem,
        mode: SkillSelectionMode,
        *,
        confidence: float | None = None,
        reason: str = "Selected manually by the user.",
    ) -> SelectedSkill:
        return SelectedSkill(
            ref=item.ref,
            version_id=item.version_id,
            version=item.version,
            manifest=item.manifest,
            selection_mode=mode,
            confidence=confidence,
            reason=reason.strip()[:256],
            package_sha256=item.package_sha256,
        )

    @staticmethod
    def _missing_tools(
        item: SkillCatalogItem, available: set[str]
    ) -> list[str]:
        raw = item.manifest.allowed_tools
        if not raw:
            return []
        required = {name for name in re.split(r"[\s,]+", raw.strip()) if name}
        return sorted(required - available)

    @staticmethod
    def _skip(
        *,
        mode: SkillSelectionMode,
        code: str,
        reason: str,
        ref=None,
        requested_key: str | None = None,
    ) -> SkillSelectionSkip:
        return SkillSelectionSkip(
            ref=ref,
            requested_key=requested_key,
            selection_mode=mode,
            code=code,
            reason=reason,
        )
