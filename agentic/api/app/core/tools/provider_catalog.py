#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

from app.core.entities.app_config import A2AConfig, MCPConfig
from app.core.entities.tool_config import ToolConfig
from app.schemas.tool_config import ProviderDescriptor


_MAX_LABEL_LENGTH = 80
_MAX_DESCRIPTION_LENGTH = 320
_MAX_TAG_LENGTH = 48


def mcp_provider_id(server_name: str) -> str:
    """Return a stable namespace without exposing transport configuration."""
    raw = str(server_name).strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-._").lower()
    slug = slug or "provider"
    if raw != slug or len(slug) > 48:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        bounded_slug = slug[:48].rstrip("-._") or "provider"
        slug = f"{bounded_slug}-{digest}"
    return f"mcp.{slug}"


def build_external_provider_descriptors(
    *,
    tool_config: ToolConfig,
    mcp_config: MCPConfig | None,
    a2a_config: A2AConfig | None,
) -> list[ProviderDescriptor]:
    """Build the offline Provider Catalog without reading runtime resources."""
    descriptors: list[ProviderDescriptor] = []

    for registration in sorted(
        tool_config.registrations.values(),
        key=lambda item: item.provider_id,
    ):
        if registration.source_type != "api":
            continue
        descriptors.append(
            ProviderDescriptor(
                provider_id=registration.provider_id,
                provider_type="api",
                label=_safe_text(registration.provider_label, _MAX_LABEL_LENGTH),
                description=_safe_text(
                    registration.description,
                    _MAX_DESCRIPTION_LENGTH,
                ),
                capability_groups=_safe_values([registration.group]),
                semantic_tags=_safe_values(["api", registration.category]),
                metadata_trust="untrusted_configuration",
                enabled=registration.enabled,
                credential_state=(
                    "configured"
                    if registration.requires_credentials
                    else "not_required"
                ),
                snapshot_state="fresh",
            )
        )

    if mcp_config is not None:
        for server_name, config in sorted(mcp_config.mcpServers.items()):
            descriptors.append(
                ProviderDescriptor(
                    provider_id=mcp_provider_id(server_name),
                    provider_type="mcp",
                    label=_safe_text(server_name, _MAX_LABEL_LENGTH),
                    description=_safe_text(
                        config.description or "MCP external tool provider",
                        _MAX_DESCRIPTION_LENGTH,
                    ),
                    capability_groups=["mcp"],
                    semantic_tags=_safe_values(["mcp", config.transport.value]),
                    metadata_trust="untrusted_configuration",
                    enabled=config.enabled,
                    credential_state=(
                        "configured"
                        if config.headers or config.env
                        else "not_required"
                    ),
                    snapshot_state="missing",
                )
            )

    enabled_a2a_targets = [
        server
        for server in (a2a_config.a2a_servers if a2a_config is not None else [])
        if server.enabled
    ]
    descriptors.append(
        ProviderDescriptor(
            provider_id="a2a.remote",
            provider_type="a2a",
            label="A2A Agent",
            description=(
                f"Configured remote Agent targets: {len(enabled_a2a_targets)}"
            ),
            capability_groups=["a2a"],
            semantic_tags=["a2a", "delegation"],
            metadata_trust="untrusted_configuration",
            enabled=a2a_config is None or bool(enabled_a2a_targets),
            credential_state="not_required",
            snapshot_state="missing",
        )
    )
    return descriptors


def _safe_values(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = _safe_text(value, _MAX_TAG_LENGTH)
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _safe_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    text = "".join(character for character in text if character.isprintable())
    return text[:limit]
