import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.core.exceptions import FailException
from app.core.language_model.entities import BaseLanguageModel


@dataclass(frozen=True)
class ProviderRuntime:
    api_key_env: str | None
    base_url_env: str
    default_base_url: str
    requires_api_key: bool = True


@dataclass(frozen=True)
class ChatToolCall:
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    parse_error: str = ""


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    message: dict[str, Any]
    tool_calls: list[ChatToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


PROVIDER_RUNTIMES: dict[str, ProviderRuntime] = {
    "openai": ProviderRuntime("OPENAI_API_KEY", "OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "deepseek": ProviderRuntime("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "moonshot": ProviderRuntime("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
    "tongyi": ProviderRuntime("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "ollama": ProviderRuntime(None, "OLLAMA_BASE_URL", "http://localhost:11434/v1", requires_api_key=False),
}


class ChatCompletionRuntime:
    def complete(
        self,
        model: BaseLanguageModel,
        query: str,
        system_prompt: str = "",
        history: list[dict[str, str]] | None = None,
        image_urls: list[str] | None = None,
        timeout: float = 60.0,
    ) -> str:
        return self.create_response(
            model=model,
            query=query,
            system_prompt=system_prompt,
            history=history,
            image_urls=image_urls,
            timeout=timeout,
        ).content

    def create_response(
        self,
        model: BaseLanguageModel,
        query: str = "",
        system_prompt: str = "",
        history: list[dict[str, Any]] | None = None,
        image_urls: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
        timeout: float = 60.0,
    ) -> ChatCompletionResult:
        runtime_config = model.metadata.get("runtime", {}) if isinstance(model.metadata, dict) else {}
        if runtime_config:
            api_key = str(runtime_config.get("api_key") or "")
            base_url = str(runtime_config.get("base_url") or "").rstrip("/")
            requires_api_key = bool(runtime_config.get("requires_api_key", True))
            if requires_api_key and not api_key:
                raise FailException("Missing provider credential")
            if not base_url:
                raise FailException("Language model provider base URL is not configured")
        else:
            runtime = PROVIDER_RUNTIMES.get(model.provider)
            if runtime is None:
                raise FailException(f"Unsupported language model provider: {model.provider}")

            settings = get_settings()
            api_key = settings.provider_api_key(runtime.api_key_env)
            if runtime.requires_api_key and not api_key:
                raise FailException(f"Missing provider credential: {runtime.api_key_env}")

            base_url = settings.provider_base_url(runtime.base_url_env, runtime.default_base_url).rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model.model,
            "messages": messages or self._build_messages(system_prompt, history or [], query, image_urls or []),
            **self._safe_parameters(model.parameters),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        if response.status_code >= 400:
            raise FailException(f"Language model request failed: {response.status_code} {response.text[:500]}")

        body = response.json()
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise FailException("Language model response format is invalid") from exc

        return ChatCompletionResult(
            content=str(message.get("content") or ""),
            message=self._normalize_assistant_message(message),
            tool_calls=self._parse_tool_calls(message),
            usage=body.get("usage") or {},
        )

    @staticmethod
    def _build_messages(
        system_prompt: str,
        history: list[dict[str, str]],
        query: str,
        image_urls: list[str],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        if image_urls:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        *[{"type": "image_url", "image_url": {"url": image_url}} for image_url in image_urls],
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _safe_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "max_tokens",
            "stop",
            "thinking",
            "reasoning_effort",
            "response_format",
        }
        return {key: value for key, value in parameters.items() if key in allowed and value is not None}

    @classmethod
    def _normalize_assistant_message(cls, message: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        if message.get("reasoning_content"):
            normalized["reasoning_content"] = message["reasoning_content"]
        tool_calls = [
            cls._to_assistant_tool_call_payload(tool_call)
            for tool_call in cls._normalize_tool_call_payloads(message)
            if tool_call.get("function", {}).get("name")
        ]
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        return normalized

    @classmethod
    def _parse_tool_calls(cls, message: dict[str, Any]) -> list[ChatToolCall]:
        parsed: list[ChatToolCall] = []
        for raw_tool_call in cls._normalize_tool_call_payloads(message):
            function = raw_tool_call.get("function") if isinstance(raw_tool_call.get("function"), dict) else {}
            name = str(function.get("name") or raw_tool_call.get("name") or "")
            if not name:
                continue
            raw_args = function.get("arguments", raw_tool_call.get("arguments", {}))
            args, parse_error = cls._parse_tool_args_with_error(raw_args)
            parsed.append(
                ChatToolCall(
                    id=str(raw_tool_call.get("id") or uuid4()),
                    name=name,
                    args=args,
                    parse_error=parse_error,
                )
            )
        return parsed

    @classmethod
    def _normalize_tool_call_payloads(cls, message: dict[str, Any]) -> list[dict[str, Any]]:
        raw_tool_calls = cls._coerce_tool_call_list(
            message.get("tool_calls")
            or (
                message.get("additional_kwargs", {}).get("tool_calls")
                if isinstance(message.get("additional_kwargs"), dict)
                else None
            )
        )
        if raw_tool_calls:
            return [cls._normalize_tool_call_payload(raw_tool_call) for raw_tool_call in raw_tool_calls]

        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            return [
                {
                    "id": str(function_call.get("id") or uuid4()),
                    "type": "function",
                    "function": {
                        "name": function_call.get("name") or "",
                        "arguments": function_call.get("arguments", {}),
                    },
                }
            ]
        return []

    @staticmethod
    def _coerce_tool_call_list(raw_tool_calls: Any) -> list[dict[str, Any]]:
        if isinstance(raw_tool_calls, dict):
            raw_tool_calls = [raw_tool_calls]
        if not isinstance(raw_tool_calls, list):
            return []
        return [raw_tool_call for raw_tool_call in raw_tool_calls if isinstance(raw_tool_call, dict)]

    @classmethod
    def _normalize_tool_call_payload(cls, raw_tool_call: dict[str, Any]) -> dict[str, Any]:
        function = raw_tool_call.get("function") if isinstance(raw_tool_call.get("function"), dict) else {}
        name = str(function.get("name") or raw_tool_call.get("name") or "")
        arguments = function.get("arguments", raw_tool_call.get("arguments", {}))
        return {
            "id": str(raw_tool_call.get("id") or uuid4()),
            "type": raw_tool_call.get("type") or "function",
            "function": {
                "name": name,
                "arguments": arguments,
            },
        }

    @classmethod
    def _to_assistant_tool_call_payload(cls, tool_call: dict[str, Any]) -> dict[str, Any]:
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        return {
            "id": str(tool_call.get("id") or uuid4()),
            "type": tool_call.get("type") or "function",
            "function": {
                "name": str(function.get("name") or ""),
                "arguments": cls._serialize_tool_arguments(function.get("arguments", {})),
            },
        }

    @staticmethod
    def _serialize_tool_arguments(arguments: Any) -> str:
        if isinstance(arguments, str):
            return arguments
        return json.dumps(arguments, ensure_ascii=False, default=str)

    @staticmethod
    def _parse_tool_args(raw_args: Any) -> dict[str, Any]:
        return ChatCompletionRuntime._parse_tool_args_with_error(raw_args)[0]

    @classmethod
    def _parse_tool_args_with_error(cls, raw_args: Any) -> tuple[dict[str, Any], str]:
        if isinstance(raw_args, dict):
            return raw_args, ""
        if isinstance(raw_args, list):
            dict_args = cls._parse_name_value_args(raw_args)
            if dict_args is not None:
                return dict_args, ""
            return {}, "Tool call arguments must be a JSON object."
        if raw_args is None or raw_args == "":
            return {}, ""

        text = cls._strip_json_fence(str(raw_args).strip())
        value, error = cls._loads_tool_args(text)
        if error:
            return {}, error
        if isinstance(value, str):
            nested_value, nested_error = cls._loads_tool_args(cls._strip_json_fence(value.strip()))
            if not nested_error:
                value = nested_value
        if isinstance(value, dict):
            return value, ""
        return {}, "Tool call arguments must be a JSON object."

    @staticmethod
    def _parse_name_value_args(raw_args: list[Any]) -> dict[str, Any] | None:
        parsed: dict[str, Any] = {}
        for item in raw_args:
            if not isinstance(item, dict) or not item.get("name"):
                return None
            parsed[str(item["name"])] = item.get("value")
        return parsed

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text

    @staticmethod
    def _loads_tool_args(text: str) -> tuple[Any, str]:
        try:
            return json.loads(text), ""
        except json.JSONDecodeError as exc:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text)
            if cleaned != text:
                try:
                    return json.loads(cleaned), ""
                except json.JSONDecodeError:
                    pass
            return {}, f"Tool call arguments are invalid JSON: {exc.msg}."
