from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import ValidateErrorException


class ParameterType(StrEnum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"


ParameterTypeMap = {
    ParameterType.STR: str,
    ParameterType.INT: int,
    ParameterType.FLOAT: float,
    ParameterType.BOOL: bool,
}


class ParameterIn(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    REQUEST_BODY = "request_body"


class OpenAPISchema(BaseModel):
    server: str = Field(default="", validate_default=True)
    description: str = Field(default="", validate_default=True)
    paths: dict[str, dict] = Field(default_factory=dict, validate_default=True)

    @field_validator("server", mode="before")
    @classmethod
    def validate_server(cls, server: str) -> str:
        if server is None or server == "":
            raise ValidateErrorException("server cannot be empty and must be a string")
        return server

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, description: str) -> str:
        if description is None or description == "":
            raise ValidateErrorException("description cannot be empty and must be a string")
        return description

    @field_validator("paths", mode="before")
    @classmethod
    def validate_paths(cls, paths: dict[str, dict]) -> dict[str, dict]:
        if not paths or not isinstance(paths, dict):
            raise ValidateErrorException("openapi_schema.paths cannot be empty and must be a dict")

        interfaces = []
        for path, path_item in paths.items():
            for method in ["get", "post"]:
                if method in path_item:
                    interfaces.append({"path": path, "method": method, "operation": path_item[method]})

        operation_ids: list[str] = []
        normalized_paths: dict[str, dict] = {}
        for interface in interfaces:
            operation = interface["operation"]
            if not isinstance(operation.get("description"), str):
                raise ValidateErrorException("operation.description cannot be empty and must be a string")
            if not isinstance(operation.get("operationId"), str):
                raise ValidateErrorException("operation.operationId cannot be empty and must be a string")
            if not isinstance(operation.get("parameters", []), list):
                raise ValidateErrorException("operation.parameters must be a list")

            operation_id = operation["operationId"]
            if operation_id in operation_ids:
                raise ValidateErrorException(f"operationId must be unique: {operation_id}")
            operation_ids.append(operation_id)

            normalized_parameters = []
            for parameter in operation.get("parameters", []):
                cls._validate_parameter(parameter)
                normalized_parameters.append(
                    {
                        "name": parameter.get("name"),
                        "in": parameter.get("in"),
                        "description": parameter.get("description"),
                        "required": parameter.get("required"),
                        "type": parameter.get("type"),
                    }
                )

            normalized_paths[interface["path"]] = {
                interface["method"]: {
                    "description": operation["description"],
                    "operationId": operation_id,
                    "parameters": normalized_parameters,
                }
            }

        return normalized_paths

    @staticmethod
    def _validate_parameter(parameter: dict) -> None:
        if not isinstance(parameter.get("name"), str):
            raise ValidateErrorException("parameter.name must be a non-empty string")
        if not isinstance(parameter.get("description"), str):
            raise ValidateErrorException("parameter.description must be a string")
        if not isinstance(parameter.get("required"), bool):
            raise ValidateErrorException("parameter.required must be a bool")
        if parameter.get("in") not in {item.value for item in ParameterIn}:
            raise ValidateErrorException("parameter.in is invalid")
        if parameter.get("type") not in {item.value for item in ParameterType}:
            raise ValidateErrorException("parameter.type is invalid")

