from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field, create_model

from app.core.tools.api_tools.entities import ParameterIn, ParameterTypeMap, ToolEntity


@dataclass
class ApiRuntimeTool:
    name: str
    description: str
    args_schema: type[BaseModel]
    func: Callable[..., str]

    def invoke(self, tool_input: dict[str, Any] | None = None, **kwargs: Any) -> str:
        payload = {**(tool_input or {}), **kwargs}
        return self.func(**payload)

    def run(self, **kwargs: Any) -> str:
        return self.func(**kwargs)

    def __call__(self, **kwargs: Any) -> str:
        return self.func(**kwargs)


class ApiProviderManager(BaseModel):
    @classmethod
    def _create_tool_func_from_tool_entity(cls, tool_entity: ToolEntity) -> Callable[..., str]:
        def tool_func(**kwargs: Any) -> str:
            parameters: dict[ParameterIn, dict[str, Any]] = {
                ParameterIn.PATH: {},
                ParameterIn.HEADER: {},
                ParameterIn.QUERY: {},
                ParameterIn.COOKIE: {},
                ParameterIn.REQUEST_BODY: {},
            }
            parameter_map = {parameter.get("name"): parameter for parameter in tool_entity.parameters}
            header_map = {header.get("key"): header.get("value") for header in tool_entity.headers}

            for key, value in kwargs.items():
                parameter = parameter_map.get(key)
                if parameter is None:
                    continue
                parameter_in = ParameterIn(parameter.get("in", ParameterIn.QUERY))
                parameters[parameter_in][key] = value

            response = httpx.request(
                method=tool_entity.method,
                url=tool_entity.url.format(**parameters[ParameterIn.PATH]),
                params=parameters[ParameterIn.QUERY],
                json=parameters[ParameterIn.REQUEST_BODY],
                headers={**header_map, **parameters[ParameterIn.HEADER]},
                cookies=parameters[ParameterIn.COOKIE],
                timeout=30.0,
            )
            response.raise_for_status()
            return response.text

        return tool_func

    @classmethod
    def _create_model_from_parameters(cls, parameters: list[dict]) -> type[BaseModel]:
        fields: dict[str, Any] = {}
        for parameter in parameters:
            field_name = parameter.get("name")
            field_type = ParameterTypeMap.get(parameter.get("type"), str)
            field_required = parameter.get("required", True)
            field_description = parameter.get("description", "")
            default = ... if field_required else None
            fields[field_name] = (field_type, Field(default=default, description=field_description))
        return create_model("DynamicApiToolInput", **fields)

    def get_tool(self, tool_entity: ToolEntity) -> ApiRuntimeTool:
        return ApiRuntimeTool(
            func=self._create_tool_func_from_tool_entity(tool_entity),
            name=f"{tool_entity.id}_{tool_entity.name}",
            description=tool_entity.description,
            args_schema=self._create_model_from_parameters(tool_entity.parameters),
        )

