import json
import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidateErrorException
from app.core.tools.api_tools.entities import OpenAPISchema
from app.models.account import Account
from app.models.api_tool import ApiTool, ApiToolProvider
from app.services.base_service import BaseService


@dataclass
class ApiToolService(BaseService):
    def update_api_tool_provider(
        self,
        session: Session,
        provider_id: UUID,
        name: str,
        icon: str,
        openapi_schema: str,
        headers: list,
        account: Account,
    ) -> None:
        api_tool_provider = self.get_api_tool_provider(session, provider_id, account)
        parsed = self.parse_openapi_schema(openapi_schema)

        duplicated = (
            session.query(ApiToolProvider)
            .filter(
                ApiToolProvider.account_id == account.id,
                ApiToolProvider.name == name,
                ApiToolProvider.id != api_tool_provider.id,
            )
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"API tool provider name already exists: {name}")

        session.execute(
            sql_delete(ApiTool).where(
                ApiTool.provider_id == api_tool_provider.id,
                ApiTool.account_id == account.id,
            )
        )
        self.update(
            session,
            api_tool_provider,
            name=name,
            icon=icon,
            headers=headers,
            description=parsed.description,
            openapi_schema=openapi_schema,
        )
        self._create_tools_from_schema(session, parsed, api_tool_provider.id, account)

    def get_api_tool_providers_with_page(
        self,
        session: Session,
        account: Account,
        search_word: str = "",
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int, int]:
        query = session.query(ApiToolProvider).filter(ApiToolProvider.account_id == account.id)
        if search_word:
            query = query.filter(ApiToolProvider.name.ilike(f"%{search_word}%"))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        providers = (
            query.order_by(desc(ApiToolProvider.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(providers), total_record, total_page

    def get_api_tool(self, session: Session, provider_id: UUID, tool_name: str, account: Account) -> ApiTool:
        api_tool = (
            session.query(ApiTool)
            .filter(ApiTool.provider_id == provider_id, ApiTool.name == tool_name)
            .one_or_none()
        )
        if api_tool is None or api_tool.account_id != account.id:
            raise NotFoundException("API tool does not exist")
        return api_tool

    def get_api_tool_provider(self, session: Session, provider_id: UUID, account: Account) -> ApiToolProvider:
        api_tool_provider = self.get(session, ApiToolProvider, provider_id)
        if api_tool_provider is None or api_tool_provider.account_id != account.id:
            raise NotFoundException("API tool provider does not exist")
        return api_tool_provider

    def create_api_tool(
        self,
        session: Session,
        name: str,
        icon: str,
        openapi_schema: str,
        headers: list,
        account: Account,
    ) -> None:
        parsed = self.parse_openapi_schema(openapi_schema)
        duplicated = (
            session.query(ApiToolProvider)
            .filter(ApiToolProvider.account_id == account.id, ApiToolProvider.name == name)
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"API tool provider name already exists: {name}")

        api_tool_provider = self.create(
            session,
            ApiToolProvider,
            account_id=account.id,
            name=name,
            icon=icon,
            description=parsed.description,
            openapi_schema=openapi_schema,
            headers=headers,
        )
        self._create_tools_from_schema(session, parsed, api_tool_provider.id, account)

    def delete_api_tool_provider(self, session: Session, provider_id: UUID, account: Account) -> None:
        api_tool_provider = self.get_api_tool_provider(session, provider_id, account)
        session.execute(sql_delete(ApiTool).where(ApiTool.provider_id == provider_id, ApiTool.account_id == account.id))
        self.delete(session, api_tool_provider)

    @classmethod
    def parse_openapi_schema(cls, openapi_schema_str: str) -> OpenAPISchema:
        try:
            data = json.loads(openapi_schema_str.strip())
            if not isinstance(data, dict):
                raise ValueError
        except Exception as exc:
            raise ValidateErrorException("OpenAPI schema must be a valid JSON object") from exc
        return OpenAPISchema(**data)

    def _create_tools_from_schema(
        self,
        session: Session,
        parsed: OpenAPISchema,
        provider_id: UUID,
        account: Account,
    ) -> None:
        for path, path_item in parsed.paths.items():
            for method, method_item in path_item.items():
                self.create(
                    session,
                    ApiTool,
                    account_id=account.id,
                    provider_id=provider_id,
                    name=method_item.get("operationId"),
                    description=method_item.get("description"),
                    url=f"{parsed.server}{path}",
                    method=method,
                    parameters=method_item.get("parameters", []),
                )

