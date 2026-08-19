#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class ToolScopeSnapshot:
    """Immutable per-Step Tool boundary used by injection and execution."""

    capabilities: tuple[str, ...] = ()
    provider_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    exact_functions: tuple[str, ...] = ()
    resolved_tool_ids: tuple[str, ...] = ()
    provider_constraint_groups: tuple[str, ...] = ()
    tool_constraint_groups: tuple[str, ...] = ()
    unknown_capabilities: tuple[str, ...] = ()
    unknown_provider_ids: tuple[str, ...] = ()
    unknown_tool_ids: tuple[str, ...] = ()


class RuntimeToolScope:
    """Mutable per-Run capability boundary shared by filtered tools."""

    SYSTEM_CAPABILITY_GROUPS = frozenset({"message"})

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._snapshot = ToolScopeSnapshot()

    @property
    def snapshot(self) -> ToolScopeSnapshot:
        return self._snapshot

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the explicitly requested, currently valid capability groups."""
        return self._snapshot.capabilities

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return self._snapshot.provider_ids

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return self._snapshot.tool_ids

    @property
    def unknown_capabilities(self) -> tuple[str, ...]:
        """Return ignored groups for diagnostics; unknown groups never grant tools."""
        return self._snapshot.unknown_capabilities

    @property
    def unknown_provider_ids(self) -> tuple[str, ...]:
        return self._snapshot.unknown_provider_ids

    @property
    def unknown_tool_ids(self) -> tuple[str, ...]:
        return self._snapshot.unknown_tool_ids

    def activate(
        self,
        capabilities: Iterable[str] | None,
        *,
        provider_ids: Iterable[str] | None = None,
        tool_ids: Iterable[str] | None = None,
        exact_functions: Iterable[str] | None = None,
        resolved_tool_ids: Iterable[str] | None = None,
    ) -> None:
        """Replace the active boundary without treating an empty list as all tools."""
        known_capabilities = self._registry.capability_groups()
        known_provider_ids = self._registry.provider_ids()
        known_tool_ids = self._registry.tool_ids()
        requested_capabilities = _normalized_values(capabilities)
        requested_provider_ids = _normalized_values(provider_ids)
        requested_tool_ids = _normalized_values(tool_ids)
        requested_resolved_tool_ids = _normalized_values(resolved_tool_ids)
        resolved_provider_ids = tuple(
            value
            for value in requested_provider_ids
            if value in known_provider_ids
        )
        resolved_tool_ids = tuple(
            value for value in requested_tool_ids if value in known_tool_ids
        )
        self._snapshot = ToolScopeSnapshot(
            capabilities=tuple(
                value
                for value in requested_capabilities
                if value in known_capabilities
            ),
            provider_ids=resolved_provider_ids,
            tool_ids=resolved_tool_ids,
            exact_functions=_normalized_values(exact_functions),
            resolved_tool_ids=tuple(
                value
                for value in requested_resolved_tool_ids
                if value in known_tool_ids and value in requested_tool_ids
            ),
            provider_constraint_groups=tuple(
                sorted(
                    self._registry.capability_groups_for_provider_ids(
                        resolved_provider_ids
                    )
                )
            ),
            tool_constraint_groups=tuple(
                sorted(
                    self._registry.capability_groups_for_tool_ids(
                        resolved_tool_ids
                    )
                )
            ),
            unknown_capabilities=tuple(
                value
                for value in requested_capabilities
                if value not in known_capabilities
            ),
            unknown_provider_ids=tuple(
                value
                for value in requested_provider_ids
                if value not in known_provider_ids
            ),
            unknown_tool_ids=tuple(
                value for value in requested_tool_ids if value not in known_tool_ids
            ),
        )

    def refresh_from_registry(self) -> None:
        """Reclassify requested IDs after lazy discovery without widening them."""
        snapshot = self._snapshot
        self.activate(
            [*snapshot.capabilities, *snapshot.unknown_capabilities],
            provider_ids=[
                *snapshot.provider_ids,
                *snapshot.unknown_provider_ids,
            ],
            tool_ids=[*snapshot.tool_ids, *snapshot.unknown_tool_ids],
            exact_functions=snapshot.exact_functions,
            resolved_tool_ids=snapshot.resolved_tool_ids,
        )

    def replace_resolved_tool_ids(self, tool_ids: Iterable[str]) -> None:
        """Replace system-validated Tool IDs produced by Provider search."""
        snapshot = self._snapshot
        if snapshot.unknown_provider_ids:
            return
        resolved: list[str] = []
        constrained_provider_groups = set(
            snapshot.provider_constraint_groups
        ).intersection(snapshot.capabilities)
        for tool_id in _normalized_values(tool_ids):
            descriptor = self._registry.get_by_tool_id(tool_id)
            if descriptor is None or descriptor.group not in snapshot.capabilities:
                continue
            if (
                descriptor.group in constrained_provider_groups
                and descriptor.provider_id not in snapshot.provider_ids
            ):
                continue
            resolved.append(tool_id)
        previous_resolved = set(snapshot.resolved_tool_ids)
        base_tool_ids = [
            tool_id
            for tool_id in [*snapshot.tool_ids, *snapshot.unknown_tool_ids]
            if tool_id not in previous_resolved
        ]
        self.activate(
            [*snapshot.capabilities, *snapshot.unknown_capabilities],
            provider_ids=[
                *snapshot.provider_ids,
                *snapshot.unknown_provider_ids,
            ],
            tool_ids=[
                *base_tool_ids,
                *resolved,
            ],
            exact_functions=snapshot.exact_functions,
            resolved_tool_ids=resolved,
        )

    def allows(self, tool_name: str, function_name: str) -> bool:
        """Check the runtime boundary before ToolConfig is evaluated."""
        snapshot = self._snapshot
        if function_name in snapshot.exact_functions:
            return True
        descriptor = self._registry.get_by_function_name(function_name)
        group = descriptor.group if descriptor else tool_name
        if group in self.SYSTEM_CAPABILITY_GROUPS:
            return True
        if group not in snapshot.capabilities:
            return False
        if descriptor is None:
            return not any(
                (
                    snapshot.provider_ids,
                    snapshot.tool_ids,
                    snapshot.unknown_provider_ids,
                    snapshot.unknown_tool_ids,
                )
            )
        if snapshot.unknown_provider_ids or snapshot.unknown_tool_ids:
            return False

        constrained_provider_groups = set(
            snapshot.provider_constraint_groups
        ).intersection(snapshot.capabilities)
        if snapshot.provider_ids and not constrained_provider_groups:
            return False
        if (
            group in constrained_provider_groups
            and descriptor.provider_id not in snapshot.provider_ids
        ):
            return False

        constrained_tool_groups = set(snapshot.tool_constraint_groups).intersection(
            snapshot.capabilities
        )
        if snapshot.tool_ids and not constrained_tool_groups:
            return False
        if (
            group in constrained_tool_groups
            and descriptor.tool_id not in snapshot.tool_ids
        ):
            return False
        return True


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
