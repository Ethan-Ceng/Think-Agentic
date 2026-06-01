from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, Session, sessionmaker

from app.core.config import Settings
from app.models.base import Base

engine = None
SessionLocal: sessionmaker[Session] | None = None


@dataclass
class Pagination:
    items: list[Any]
    total: int
    page: int
    per_page: int


class SQLAlchemy:
    """Compatibility facade for legacy services while using FastAPI DI."""

    Model = Base
    metadata = Base.metadata

    def __init__(self, session: Session):
        self.session = session

    @contextmanager
    def auto_commit(self) -> Generator[None, None, None]:
        try:
            yield
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        try:
            yield self.session
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def paginate(self, query: Query[Any], page: int = 1, per_page: int = 20, error_out: bool = False) -> Pagination:
        page = max(int(page or 1), 1)
        per_page = max(int(per_page or 20), 1)
        total = int(query.order_by(None).count())
        items = list(query.limit(per_page).offset((page - 1) * per_page).all())
        return Pagination(items=items, total=total, page=page, per_page=per_page)


def init_database(settings: Settings) -> None:
    global engine, SessionLocal
    if engine is not None and SessionLocal is not None:
        return
    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle,
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def close_database() -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    engine = None
    SessionLocal = None


def get_session() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_facade() -> Generator[SQLAlchemy, None, None]:
    for session in get_session():
        yield SQLAlchemy(session)
