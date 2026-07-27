#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Iterable

from app.core.tools.registry import ToolRegistry


class RuntimeToolScope:
    """Mutable per-Run capability boundary shared by filtered tools."""

    SYSTEM_CAPABILITY_GROUPS = frozenset({"message"})

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._capabilities: tuple[str, ...] = ()
        self._unknown_capabilities: tuple[str, ...] = ()
        self._exact_functions: frozenset[str] = frozenset()

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the explicitly requested, currently valid capability groups."""
        return self._capabilities

    @property
    def unknown_capabilities(self) -> tuple[str, ...]:
        """Return ignored groups for diagnostics; unknown groups never grant tools."""
        return self._unknown_capabilities

    def activate(
        self,
        capabilities: Iterable[str] | None,
        *,
        exact_functions: Iterable[str] | None = None,
    ) -> None:
        """Replace the active boundary without treating an empty list as all tools."""
        known = self._registry.capability_groups()
        requested = _normalized_values(capabilities)
        self._capabilities = tuple(value for value in requested if value in known)
        self._unknown_capabilities = tuple(
            value for value in requested if value not in known
        )
        self._exact_functions = frozenset(_normalized_values(exact_functions))

    def allows(self, tool_name: str, function_name: str) -> bool:
        """Check the runtime boundary before ToolConfig is evaluated."""
        if function_name in self._exact_functions:
            return True
        descriptor = self._registry.get_by_function_name(function_name)
        group = descriptor.group if descriptor else tool_name
        return (
            group in self.SYSTEM_CAPABILITY_GROUPS
            or group in self._capabilities
        )


def _normalized_values(values: Iterable[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)
