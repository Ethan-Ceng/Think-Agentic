#!/usr/bin/env python
# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Iterable

from app.services.tool_capability_service import ToolCapabilityService
from app.schemas.tool_config import (
    ToolCapabilitySummary,
    ToolConfig,
    ToolPreflightCheck,
    ToolPreflightResponse,
)


@dataclass(frozen=True)
class PreflightRule:
    rule_id: str
    semantic_tag: str
    keywords: tuple[str, ...]
    error_code: str
    missing_message: str


class ToolPreflightService:
    """基于简单规则做任务执行前工具能力诊断。"""

    _RULES: tuple[PreflightRule, ...] = (
        PreflightRule(
            rule_id="shell_required",
            semantic_tag="shell",
            keywords=("运行", "执行命令", "安装", "npm", "pnpm", "pip", "pytest", "docker", "shell", "脚本"),
            error_code="capability_missing:shell",
            missing_message="当前 Shell 工具未启用，无法执行命令、安装依赖或运行脚本。",
        ),
        PreflightRule(
            rule_id="browser_required",
            semantic_tag="browser",
            keywords=("打开网页", "点击", "登录", "浏览器", "页面", "截图", "控制台", "navigate", "browser"),
            error_code="capability_missing:browser",
            missing_message="当前浏览器工具未启用，无法访问网页或操作页面。",
        ),
        PreflightRule(
            rule_id="search_required",
            semantic_tag="search",
            keywords=("最新", "今天", "新闻", "实时", "搜索", "查一下", "价格", "天气", "search"),
            error_code="capability_missing:search",
            missing_message="当前搜索工具未启用，无法获取实时或最新信息。",
        ),
        PreflightRule(
            rule_id="file_write_required",
            semantic_tag="file_write",
            keywords=("修改", "写入", "生成文件", "保存到", "替换", "创建文件", "编辑", "改代码"),
            error_code="capability_missing:file_write",
            missing_message="当前文件写入工具未启用，无法创建、修改或替换文件。",
        ),
        PreflightRule(
            rule_id="remote_agent_required",
            semantic_tag="remote_agent",
            keywords=("远程 agent", "a2a", "remote agent", "调用其他 agent", "分派给"),
            error_code="capability_missing:remote_agent",
            missing_message="当前 A2A 远程 Agent 工具未启用，无法分派任务给远程 Agent。",
        ),
    )

    def __init__(self, capability_service: ToolCapabilityService | None = None) -> None:
        self.capability_service = capability_service or ToolCapabilityService()

    def check(self, message: str, tool_config: ToolConfig) -> ToolPreflightResponse:
        summary = self.capability_service.build_summary(tool_config)
        checks = list(self._run_rules(message, summary))

        if any(not check.passed and check.error_code for check in checks):
            status = "blocked"
        elif any(not check.passed for check in checks):
            status = "warning"
        else:
            status = "pass"

        return ToolPreflightResponse(
            status=status,
            checks=checks,
            capability_snapshot=summary,
        )

    def _run_rules(
        self,
        message: str,
        summary: ToolCapabilitySummary,
    ) -> Iterable[ToolPreflightCheck]:
        normalized_message = message.lower()
        semantic_tags = set(summary.semantic_tags)
        for rule in self._RULES:
            matched = any(keyword.lower() in normalized_message for keyword in rule.keywords)
            if not matched:
                yield ToolPreflightCheck(
                    rule_id=rule.rule_id,
                    passed=True,
                    user_message="未检测到该能力需求。",
                )
                continue

            passed = rule.semantic_tag in semantic_tags
            yield ToolPreflightCheck(
                rule_id=rule.rule_id,
                passed=passed,
                error_code=None if passed else rule.error_code,
                user_message="能力可用。" if passed else rule.missing_message,
            )
