import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, create_model

from app.core.config import get_settings
from app.core.tools.builtin_tools.entities.tool_entity import ToolEntity, ToolParam, ToolParamType

DEFAULT_TOOL_PARAMS: dict[str, list[ToolParam]] = {
    "gaode_weather": [
        ToolParam(name="city", label="City", type=ToolParamType.STRING, required=True),
    ],
    "google_serper": [
        ToolParam(name="query", label="Query", type=ToolParamType.STRING, required=True),
    ],
    "duckduckgo_search": [
        ToolParam(name="query", label="Query", type=ToolParamType.STRING, required=True),
    ],
    "wikipedia_search": [
        ToolParam(name="query", label="Query", type=ToolParamType.STRING, required=True),
    ],
    "dalle3": [
        ToolParam(name="query", label="Prompt", type=ToolParamType.STRING, required=True),
        ToolParam(name="size", label="Size", type=ToolParamType.STRING, required=False, default="1024x1024"),
        ToolParam(name="style", label="Style", type=ToolParamType.STRING, required=False, default="vivid"),
    ],
}


@dataclass
class BuiltinRuntimeTool:
    name: str
    description: str
    args_schema: type[BaseModel]

    def invoke(self, tool_input: dict[str, Any] | None = None, **kwargs: Any) -> str:
        payload = {**(tool_input or {}), **kwargs}
        return self.run(**payload)

    def run(self, **kwargs: Any) -> str:
        match self.name:
            case "current_time":
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
            case "gaode_weather":
                return _gaode_weather(**kwargs)
            case "google_serper":
                return _google_serper(**kwargs)
            case "duckduckgo_search":
                return _duckduckgo_search(**kwargs)
            case "wikipedia_search":
                return _wikipedia_search(**kwargs)
            case "dalle3":
                return _dalle3(**kwargs)
            case _:
                return f"Builtin tool is not implemented: {self.name}"

    def __call__(self, **kwargs: Any) -> str:
        return self.run(**kwargs)


def get_tool_params(tool: ToolEntity) -> list[ToolParam]:
    return tool.params or DEFAULT_TOOL_PARAMS.get(tool.name, [])


def build_builtin_runtime_tool(tool: ToolEntity) -> BuiltinRuntimeTool:
    return BuiltinRuntimeTool(
        name=tool.name,
        description=tool.description,
        args_schema=_create_model_from_params(get_tool_params(tool)),
    )


def _create_model_from_params(params: list[ToolParam]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    type_map = {
        ToolParamType.STRING: str,
        ToolParamType.NUMBER: float,
        ToolParamType.BOOLEAN: bool,
        ToolParamType.SELECT: str,
    }
    for param in params:
        field_type = type_map.get(param.type, str)
        default = ... if param.required and param.default is None else param.default
        fields[param.name] = (field_type, Field(default=default, description=param.label))
    return create_model("DynamicBuiltinToolInput", **fields)


def _gaode_weather(**kwargs: Any) -> str:
    gaode_api_key = get_settings().gaode_api_key
    if not gaode_api_key:
        return "GAODE_API_KEY is not configured"

    city = kwargs.get("city", "")
    api_domain = "https://restapi.amap.com/v3"
    try:
        city_response = httpx.get(
            f"{api_domain}/config/district",
            params={"key": gaode_api_key, "keywords": city, "subdistrict": 0},
            timeout=15.0,
        )
        city_response.raise_for_status()
        city_data = city_response.json()
        if city_data.get("info") != "OK" or not city_data.get("districts"):
            return f"Failed to get weather for {city}"

        ad_code = city_data["districts"][0]["adcode"]
        weather_response = httpx.get(
            f"{api_domain}/weather/weatherInfo",
            params={"key": gaode_api_key, "city": ad_code, "extensions": "all"},
            timeout=15.0,
        )
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        if weather_data.get("info") == "OK":
            return json.dumps(weather_data, ensure_ascii=False)
        return f"Failed to get weather for {city}"
    except Exception:
        return f"Failed to get weather for {city}"


def _google_serper(**kwargs: Any) -> str:
    api_key = get_settings().serper_api_key
    if not api_key:
        return "SERPER_API_KEY is not configured"
    response = httpx.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": kwargs.get("query", "")},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.text


def _duckduckgo_search(**kwargs: Any) -> str:
    response = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": kwargs.get("query", ""), "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.text


def _wikipedia_search(**kwargs: Any) -> str:
    query = quote(str(kwargs.get("query", "")))
    response = httpx.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}", timeout=30.0)
    response.raise_for_status()
    return response.text


def _dalle3(**kwargs: Any) -> str:
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        return "OPENAI_API_KEY is not configured"
    api_base = settings.openai_base_url.rstrip("/")
    response = httpx.post(
        f"{api_base}/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "dall-e-3",
            "prompt": kwargs.get("query", ""),
            "n": 1,
            "size": kwargs.get("size", "1024x1024"),
            "style": kwargs.get("style", "vivid"),
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.text
