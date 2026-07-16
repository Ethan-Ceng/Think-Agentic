#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
import yaml

from app.core.entities.tool_config import ToolConfig, ToolRegistration
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool

logger = logging.getLogger(__name__)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
BODY_ARGUMENT = "body"
MAX_FUNCTION_NAME_LENGTH = 64
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", "host.docker.internal"}


@dataclass(frozen=True)
class APIParameterBinding:
    argument_name: str
    parameter_name: str
    location: str


@dataclass(frozen=True)
class APIToolDefinition:
    registration_id: str
    provider_id: str
    provider_label: str
    group: str
    category: str
    source_enabled: bool
    requires_sandbox: bool
    requires_browser: bool
    requires_credentials: bool
    method: str
    path: str
    base_url: str
    headers: Dict[str, str]
    timeout: float
    allow_private_network: bool
    function_name: str
    operation_id: str
    label: str
    description: str
    tool_schema: Dict[str, Any]
    parameters: List[APIParameterBinding]
    body_content_type: Optional[str] = None


class APITool(BaseTool):
    """Runtime tool package for OpenAPI-backed API registrations."""

    name = "api"

    def __init__(
        self,
        tool_config: ToolConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__()
        self.tool_config = tool_config
        self._transport = transport
        self._definitions = {
            definition.function_name: definition
            for definition in build_api_tool_definitions(tool_config)
        }

    def get_tools(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(definition.tool_schema) for definition in self._definitions.values()]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._definitions

    async def invoke(self, tool_name: str, **kwargs: Any) -> ToolResult:
        definition = self._definitions.get(tool_name)
        if definition is None:
            return ToolResult(success=False, message=f"API tool not found: {tool_name}")
        if not definition.source_enabled:
            return ToolResult(success=False, message=f"API tool source is disabled: {definition.provider_id}")
        if not definition.base_url:
            return ToolResult(
                success=False,
                message=f"API tool source [{definition.provider_id}] is missing base_url or OpenAPI servers",
            )

        request = self._build_request(definition, kwargs)
        try:
            validate_api_request_url(
                request["url"],
                allow_private_network=definition.allow_private_network,
                resolve_dns=self._transport is None,
            )
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))

        timeout = httpx.Timeout(definition.timeout)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                response = await client.request(**request)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, message=f"API request failed: {exc}")

        body = _response_body(response)
        return ToolResult(
            success=response.status_code < 400,
            message=f"{definition.method.upper()} {request['url']} -> HTTP {response.status_code}",
            data={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": body,
            },
        )

    def _build_request(self, definition: APIToolDefinition, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        headers = _resolve_headers(definition.headers)
        query: Dict[str, Any] = {}
        cookies: Dict[str, Any] = {}
        path = definition.path

        for binding in definition.parameters:
            if binding.argument_name not in kwargs:
                continue
            value = kwargs.get(binding.argument_name)
            if value is None:
                continue
            if binding.location == "path":
                encoded = quote(str(value), safe="")
                path = path.replace("{" + binding.parameter_name + "}", encoded)
            elif binding.location == "query":
                query[binding.parameter_name] = value
            elif binding.location == "header":
                headers[binding.parameter_name] = str(value)
            elif binding.location == "cookie":
                cookies[binding.parameter_name] = value

        request: Dict[str, Any] = {
            "method": definition.method.upper(),
            "url": _join_url(definition.base_url, path),
            "headers": headers,
        }
        if query:
            request["params"] = query
        if cookies:
            request["cookies"] = cookies

        if BODY_ARGUMENT in kwargs and kwargs[BODY_ARGUMENT] is not None:
            content_type = definition.body_content_type or "application/json"
            body = kwargs[BODY_ARGUMENT]
            if "json" in content_type:
                request["json"] = body
            elif "form" in content_type:
                request["data"] = body
                headers.setdefault("Content-Type", content_type)
            elif isinstance(body, str | bytes):
                request["content"] = body
                headers.setdefault("Content-Type", content_type)
            else:
                request["content"] = json.dumps(body, ensure_ascii=False)
                headers.setdefault("Content-Type", content_type)

        return request


def build_api_tool_definitions(tool_config: ToolConfig | None) -> List[APIToolDefinition]:
    if tool_config is None:
        return []

    definitions: List[APIToolDefinition] = []
    used_names: set[str] = set()
    for registration in sorted(tool_config.registrations.values(), key=lambda item: item.registration_id):
        if registration.source_type != "api" or registration.executor_type != "api":
            continue
        try:
            definitions.extend(_definitions_from_registration(registration, used_names))
        except ValueError as exc:
            logger.warning("Skipping invalid API tool registration [%s]: %s", registration.registration_id, exc)
    return definitions


def validate_api_tool_registration(registration: ToolRegistration) -> None:
    if registration.source_type != "api" or registration.executor_type != "api":
        return
    schema = parse_openapi_schema(registration.config.get("openapi_schema") or registration.config.get("schema"))
    if schema is None:
        return
    if not isinstance(schema.get("paths"), dict):
        raise ValueError("OpenAPI schema must contain a paths object")
    base_url = str(registration.config.get("base_url") or _first_server_url(schema) or "").strip()
    if base_url:
        validate_api_request_url(
            base_url,
            allow_private_network=bool(registration.config.get("allow_private_network", False)),
            resolve_dns=False,
        )


def validate_api_request_url(
    url: str,
    allow_private_network: bool = False,
    resolve_dns: bool = False,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("API tool URL must use http or https")
    if not parsed.hostname:
        raise ValueError("API tool URL must include a hostname")
    if allow_private_network:
        return

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in LOCAL_HOSTNAMES or hostname.endswith(".localhost"):
        raise ValueError("API tool URL cannot target local hostnames")

    literal_ip = _parse_ip_address(hostname)
    if literal_ip and _is_restricted_ip(literal_ip):
        raise ValueError("API tool URL cannot target private or non-global IP addresses")

    if not resolve_dns or literal_ip:
        return

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"API tool hostname cannot be resolved: {hostname}") from exc
    for address in addresses:
        ip = _parse_ip_address(address[4][0])
        if ip and _is_restricted_ip(ip):
            raise ValueError("API tool URL resolved to a private or non-global IP address")


def parse_openapi_schema(raw_schema: Any) -> Optional[Dict[str, Any]]:
    if raw_schema in (None, ""):
        return None
    if isinstance(raw_schema, dict):
        schema = raw_schema
    elif isinstance(raw_schema, str):
        try:
            loaded = json.loads(raw_schema)
        except json.JSONDecodeError:
            loaded = yaml.safe_load(raw_schema)
        if not isinstance(loaded, dict):
            raise ValueError("OpenAPI schema must be an object")
        schema = loaded
    else:
        raise ValueError("OpenAPI schema must be an object or JSON/YAML string")

    return copy.deepcopy(schema)


def api_risk_for_method(method: str) -> str:
    normalized = method.lower()
    if normalized in {"get", "head", "options"}:
        return "low"
    if normalized == "delete":
        return "high"
    return "medium"


def _definitions_from_registration(
    registration: ToolRegistration,
    used_names: set[str],
) -> List[APIToolDefinition]:
    schema = parse_openapi_schema(registration.config.get("openapi_schema") or registration.config.get("schema"))
    if schema is None:
        return []

    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI schema must contain a paths object")

    base_url = str(registration.config.get("base_url") or _first_server_url(schema) or "").strip()
    headers = _string_dict(registration.config.get("headers"))
    timeout = _timeout_value(registration.config.get("timeout"))
    allow_private_network = bool(registration.config.get("allow_private_network", False))

    definitions: List[APIToolDefinition] = []
    for path, raw_path_item in paths.items():
        path_item = _resolve_ref(raw_path_item, schema)
        if not isinstance(path_item, dict):
            continue
        common_parameters = path_item.get("parameters", [])
        for method, raw_operation in path_item.items():
            method_l = method.lower()
            if method_l not in HTTP_METHODS:
                continue
            operation = _resolve_ref(raw_operation, schema)
            if not isinstance(operation, dict):
                continue
            definitions.append(
                _definition_from_operation(
                    registration=registration,
                    schema=schema,
                    base_url=base_url,
                    headers=headers,
                    timeout=timeout,
                    allow_private_network=allow_private_network,
                    path=str(path),
                    method=method_l,
                    operation=operation,
                    common_parameters=common_parameters,
                    used_names=used_names,
                )
            )
    return definitions


def _definition_from_operation(
    registration: ToolRegistration,
    schema: Dict[str, Any],
    base_url: str,
    headers: Dict[str, str],
    timeout: float,
    allow_private_network: bool,
    path: str,
    method: str,
    operation: Dict[str, Any],
    common_parameters: Any,
    used_names: set[str],
) -> APIToolDefinition:
    operation_id = str(operation.get("operationId") or _fallback_operation_id(method, path))
    function_name = _unique_function_name(registration.provider_id, operation_id, used_names)
    label = str(operation.get("summary") or operation_id)
    description = str(operation.get("description") or operation.get("summary") or "")
    properties, required, parameter_bindings, body_content_type = _operation_parameters(
        schema=schema,
        operation=operation,
        common_parameters=common_parameters,
    )

    tool_schema = {
        "type": "function",
        "function": {
            "name": function_name,
            "description": description or label,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

    return APIToolDefinition(
        registration_id=registration.registration_id,
        provider_id=registration.provider_id,
        provider_label=registration.provider_label,
        group=registration.group,
        category=registration.category,
        source_enabled=registration.enabled,
        requires_sandbox=registration.requires_sandbox,
        requires_browser=registration.requires_browser,
        requires_credentials=registration.requires_credentials or bool(headers),
        method=method,
        path=path,
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        allow_private_network=allow_private_network,
        function_name=function_name,
        operation_id=operation_id,
        label=label,
        description=description,
        tool_schema=tool_schema,
        parameters=parameter_bindings,
        body_content_type=body_content_type,
    )


def _operation_parameters(
    schema: Dict[str, Any],
    operation: Dict[str, Any],
    common_parameters: Any,
) -> tuple[Dict[str, Any], List[str], List[APIParameterBinding], Optional[str]]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    bindings: List[APIParameterBinding] = []
    used_arguments: set[str] = set()

    for raw_parameter in [*(common_parameters or []), *(operation.get("parameters") or [])]:
        parameter = _resolve_ref(raw_parameter, schema)
        if not isinstance(parameter, dict):
            continue
        location = str(parameter.get("in") or "")
        if location not in {"path", "query", "header", "cookie"}:
            continue
        name = str(parameter.get("name") or "")
        if not name:
            continue
        argument_name = _unique_argument_name(name, location, used_arguments)
        parameter_schema = _normalize_json_schema(parameter.get("schema") or {"type": "string"}, schema)
        if parameter.get("description"):
            parameter_schema = {**parameter_schema, "description": str(parameter["description"])}
        properties[argument_name] = parameter_schema
        if parameter.get("required") or location == "path":
            required.append(argument_name)
        bindings.append(
            APIParameterBinding(
                argument_name=argument_name,
                parameter_name=name,
                location=location,
            )
        )

    body_content_type = None
    request_body = _resolve_ref(operation.get("requestBody"), schema)
    if isinstance(request_body, dict):
        content = request_body.get("content")
        if isinstance(content, dict) and content:
            body_content_type, media = _choose_media(content)
            body_schema = _normalize_json_schema(media.get("schema") if isinstance(media, dict) else None, schema)
            properties[BODY_ARGUMENT] = {
                **body_schema,
                "description": "HTTP request body.",
            }
            if request_body.get("required"):
                required.append(BODY_ARGUMENT)

    return properties, required, bindings, body_content_type


def _choose_media(content: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        if media_type in content and isinstance(content[media_type], dict):
            return media_type, content[media_type]
    for media_type, media in content.items():
        if isinstance(media, dict):
            return str(media_type), media
    return "application/json", {}


def _normalize_json_schema(raw_schema: Any, root_schema: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _resolve_ref(raw_schema, root_schema)
    if not isinstance(resolved, dict):
        return {"type": "string"}

    normalized = copy.deepcopy(resolved)
    if "type" not in normalized:
        if "properties" in normalized:
            normalized["type"] = "object"
        elif "items" in normalized:
            normalized["type"] = "array"
        else:
            normalized["type"] = "string"
    return normalized


def _resolve_ref(value: Any, root: Dict[str, Any], depth: int = 0) -> Any:
    if depth > 20:
        return value
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        ref = value["$ref"]
        if not ref.startswith("#/"):
            return value
        target: Any = root
        for part in ref[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or key not in target:
                return value
            target = target[key]
        merged = copy.deepcopy(_resolve_ref(target, root, depth + 1))
        if isinstance(merged, dict):
            siblings = {k: v for k, v in value.items() if k != "$ref"}
            merged.update(siblings)
        return merged
    if isinstance(value, dict):
        return {key: _resolve_ref(item, root, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_ref(item, root, depth + 1) for item in value]
    return value


def _unique_argument_name(name: str, location: str, used_arguments: set[str]) -> str:
    candidate = _sanitize_token(name)
    if not candidate:
        candidate = f"{location}_param"
    if candidate not in used_arguments:
        used_arguments.add(candidate)
        return candidate
    candidate = f"{location}_{candidate}"
    if candidate not in used_arguments:
        used_arguments.add(candidate)
        return candidate

    index = 2
    while f"{candidate}_{index}" in used_arguments:
        index += 1
    unique = f"{candidate}_{index}"
    used_arguments.add(unique)
    return unique


def _unique_function_name(provider_id: str, operation_id: str, used_names: set[str]) -> str:
    provider = _sanitize_token(provider_id)
    operation = _sanitize_token(operation_id)
    provider_prefix = provider if provider.startswith("api_") else f"api_{provider}"
    candidate = _limit_function_name(f"{provider_prefix}_{operation}", f"{provider_id}:{operation_id}")
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    index = 2
    while True:
        suffix = f"_{index}"
        unique = _limit_function_name(
            f"{candidate[: MAX_FUNCTION_NAME_LENGTH - len(suffix)]}{suffix}",
            f"{provider_id}:{operation_id}:{index}",
        )
        if unique not in used_names:
            used_names.add(unique)
            return unique
        index += 1


def _limit_function_name(value: str, seed: str) -> str:
    if len(value) <= MAX_FUNCTION_NAME_LENGTH:
        return value
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"{value[: MAX_FUNCTION_NAME_LENGTH - 9]}_{digest}"


def _sanitize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_").lower()
    return token or "tool"


def _fallback_operation_id(method: str, path: str) -> str:
    path_part = re.sub(r"[{}]", "", path.strip("/").replace("/", "_"))
    return f"{method}_{path_part or 'root'}"


def _first_server_url(schema: Dict[str, Any]) -> Optional[str]:
    servers = schema.get("servers")
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, dict) and server.get("url"):
                return str(server["url"])
    return None


def _string_dict(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _timeout_value(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 60.0
    return min(max(timeout, 1.0), 600.0)


def _parse_ip_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_restricted_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global


def _resolve_headers(headers: Dict[str, str]) -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    for key, value in headers.items():
        header_value = _resolve_config_value(value)
        if header_value:
            resolved[key] = header_value
    return resolved


def _resolve_config_value(value: str) -> str:
    if value.startswith("env:"):
        return os.environ.get(value[4:], "")
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized_path}"


def _response_body(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return response.json()
        except ValueError:
            pass
    text = response.text
    if len(text) > 20000:
        return f"{text[:20000]}...[truncated]"
    return text
