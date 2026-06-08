#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
from typing import Any, Dict, Iterable, List

from app.core.tools.registry import ToolRegistry
from app.schemas.tool_config import ToolCapabilitySummary, ToolConfig, ToolDescriptor


class ToolCapabilityService:
    """根据工具配置生成能力摘要。"""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()

    def build_summary(self, tool_config: ToolConfig) -> ToolCapabilitySummary:
        descriptors = self.registry.apply_config(tool_config, effective=True)
        enabled = [descriptor for descriptor in descriptors if descriptor.enabled]
        return ToolCapabilitySummary(
            executor_types=sorted({descriptor.executor_type for descriptor in enabled}),
            semantic_tags=sorted(self._semantic_tags(enabled)),
            tool_names=sorted({descriptor.function_name for descriptor in enabled}),
            constraints=self._constraints(enabled),
            generated_at=int(time.time()),
        )

    def _semantic_tags(self, descriptors: Iterable[ToolDescriptor]) -> set[str]:
        tags: set[str] = set()
        for descriptor in descriptors:
            function_name = descriptor.function_name
            if descriptor.group == "file":
                tags.add("file")
                tags.add("file_write" if function_name in {"write_file", "replace_in_file"} else "file_read")
            elif descriptor.group == "shell":
                tags.add("shell")
            elif descriptor.group == "browser":
                tags.add("browser")
                if function_name == "browser_console_exec":
                    tags.add("browser_script")
            elif descriptor.group == "search":
                tags.add("search")
                tags.add("realtime")
            elif descriptor.group == "message":
                tags.add("user_interaction")
            elif descriptor.group == "a2a":
                tags.add("remote_agent")
        return tags

    def _constraints(self, descriptors: List[ToolDescriptor]) -> Dict[str, Any]:
        return {
            "requires_sandbox": any(descriptor.requires_sandbox for descriptor in descriptors),
            "requires_browser": any(descriptor.requires_browser for descriptor in descriptors),
            "requires_credentials": any(descriptor.requires_credentials for descriptor in descriptors),
            "high_risk_tool_count": sum(1 for descriptor in descriptors if descriptor.risk_level == "high"),
        }
