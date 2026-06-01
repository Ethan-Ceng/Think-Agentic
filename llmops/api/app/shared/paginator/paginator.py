import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Query, Session


class PaginatorReq(BaseModel):
    """Legacy-compatible pagination request."""

    model_config = ConfigDict(populate_by_name=True)

    current_page: int = Field(1, ge=1, le=9999, alias="page")
    page_size: int = Field(20, ge=1, le=50)


@dataclass
class Paginator:
    total_page: int = 0
    total_record: int = 0
    current_page: int = 1
    page_size: int = 20

    def __init__(self, db: Session, req: PaginatorReq | None = None):
        if req is not None:
            self.current_page = req.current_page
            self.page_size = req.page_size
        self.db = db

    def paginate(self, statement: Query[Any] | Select[Any]) -> list[Any]:
        if isinstance(statement, Query):
            return self._paginate_query(statement)
        return self._paginate_select(statement)

    def _paginate_query(self, query: Query[Any]) -> list[Any]:
        self.total_record = int(query.order_by(None).count())
        self.total_page = math.ceil(self.total_record / self.page_size)
        return list(query.limit(self.page_size).offset(self._offset).all())

    def _paginate_select(self, statement: Select[Any]) -> list[Any]:
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        self.total_record = int(self.db.execute(count_statement).scalar_one() or 0)
        self.total_page = math.ceil(self.total_record / self.page_size)

        result = self.db.execute(statement.limit(self.page_size).offset(self._offset))
        if self._should_return_scalars(statement):
            return list(result.scalars().all())
        return list(result.all())

    @property
    def _offset(self) -> int:
        return (self.current_page - 1) * self.page_size

    @staticmethod
    def _should_return_scalars(statement: Select[Any]) -> bool:
        column_descriptions = getattr(statement, "column_descriptions", None)
        return bool(column_descriptions and len(column_descriptions) == 1)


@dataclass
class PageModel:
    list: list[Any]
    paginator: Paginator

