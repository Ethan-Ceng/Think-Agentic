from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.models.api_tool import ApiTool, ApiToolProvider


class HeaderItem(BaseModel):
    key: str
    value: str


class ValidateOpenAPISchemaRequest(BaseModel):
    openapi_schema: str


class CreateApiToolRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=30)
    icon: HttpUrl
    openapi_schema: str
    headers: list[HeaderItem] = Field(default_factory=list)


class UpdateApiToolProviderRequest(CreateApiToolRequest):
    pass


class ApiToolProviderResponse(BaseModel):
    id: UUID
    name: str
    icon: str
    openapi_schema: str
    headers: list[dict] = Field(default_factory=list)
    created_at: int = 0

    @classmethod
    def from_provider(cls, provider: ApiToolProvider) -> "ApiToolProviderResponse":
        return cls(
            id=provider.id,
            name=provider.name,
            icon=provider.icon,
            openapi_schema=provider.openapi_schema,
            headers=provider.headers or [],
            created_at=int(provider.created_at.timestamp()) if provider.created_at else 0,
        )


class ApiToolResponse(BaseModel):
    id: UUID
    name: str
    description: str
    inputs: list[dict] = Field(default_factory=list)
    provider: dict = Field(default_factory=dict)

    @classmethod
    def from_tool(cls, tool: ApiTool) -> "ApiToolResponse":
        provider = tool.provider
        return cls(
            id=tool.id,
            name=tool.name,
            description=tool.description or "",
            inputs=[{k: v for k, v in param.items() if k != "in"} for param in (tool.parameters or [])],
            provider={
                "id": provider.id,
                "name": provider.name,
                "icon": provider.icon,
                "description": provider.description,
                "headers": provider.headers,
            },
        )


class ApiToolProviderPageItem(BaseModel):
    id: UUID
    name: str
    icon: str
    description: str
    headers: list[dict] = Field(default_factory=list)
    tools: list[dict] = Field(default_factory=list)
    created_at: int = 0

    @classmethod
    def from_provider(cls, provider: ApiToolProvider) -> "ApiToolProviderPageItem":
        return cls(
            id=provider.id,
            name=provider.name,
            icon=provider.icon,
            description=provider.description or "",
            headers=provider.headers or [],
            tools=[
                {
                    "id": str(tool.id),
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputs": [{k: v for k, v in param.items() if k != "in"} for param in (tool.parameters or [])],
                }
                for tool in provider.tools
            ],
            created_at=int(provider.created_at.timestamp()) if provider.created_at else 0,
        )

