import asyncio
from datetime import datetime

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.core.entities.project import (
    Project,
    ProjectNameConflictError,
    ProjectNotFoundError,
)
from app.core.entities.session import Session
from app.models.project import ProjectModel
from app.models.session import SessionModel
from app.repositories.db_project_repository import DBProjectRepository


class _Result:
    def __init__(self, *, scalar=None, scalars=None, rowcount=0):
        self._scalar = scalar
        self._scalars = list(scalars or [])
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeDBSession:
    def __init__(self, *results, flush_error=None):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.flush_error = flush_error
        self.flush_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)

    def add(self, record):
        self.added.append(record)

    def begin_nested(self):
        return _NestedTransaction()

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            error = self.flush_error
            self.flush_error = None
            raise error


def _record(
    *,
    project_id: str = "project-1",
    user_id: str = "user-1",
    name: str = "Alpha",
    created_at: datetime | None = None,
) -> ProjectModel:
    timestamp = created_at or datetime.now()
    return ProjectModel(
        id=project_id,
        user_id=user_id,
        name=name,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_project_model_is_minimal_single_level_and_round_trips():
    project = Project(user_id="user-1", name="Alpha")

    record = ProjectModel.from_domain(project)
    record.created_at = project.created_at
    record.updated_at = project.updated_at

    assert record.to_domain() == project
    assert set(ProjectModel.__table__.columns.keys()) == {
        "id",
        "user_id",
        "name",
        "created_at",
        "updated_at",
    }
    assert "parent_id" not in ProjectModel.__table__.columns
    assert {index.name for index in ProjectModel.__table__.indexes} == {
        "ix_projects_user_created_at",
        "ux_projects_user_lower_name",
    }


def test_session_model_round_trips_nullable_project_and_uses_set_null_fk():
    session = Session(user_id="user-1", project_id="project-1")

    record = SessionModel.from_domain(session)
    record.created_at = session.created_at
    record.updated_at = session.updated_at
    restored = record.to_domain()

    foreign_key = next(iter(SessionModel.__table__.c.project_id.foreign_keys))
    assert restored.project_id == "project-1"
    assert foreign_key.ondelete == "SET NULL"
    assert foreign_key.target_fullname == "projects.id"
    assert "ix_sessions_user_project_id" in {
        index.name for index in SessionModel.__table__.indexes
    }


def test_list_is_user_scoped_and_stably_ordered():
    async def scenario():
        first = _record(project_id="project-a", name="Alpha")
        second = _record(project_id="project-b", name="Beta")
        fake = _FakeDBSession(_Result(scalars=[first, second]))
        repository = DBProjectRepository(fake)

        projects = await repository.list_by_user("user-1")

        statement = _sql(fake.statements[0])
        assert [project.id for project in projects] == ["project-a", "project-b"]
        assert "projects.user_id = 'user-1'" in statement
        assert "ORDER BY projects.created_at DESC, projects.id DESC" in statement

    asyncio.run(scenario())


def test_get_hides_missing_and_cross_user_projects():
    async def scenario():
        fake = _FakeDBSession(_Result(scalar=None))
        repository = DBProjectRepository(fake)

        project = await repository.get_by_id_for_user("project-1", "other-user")

        statement = _sql(fake.statements[0])
        postgres_statement = _postgres_sql(fake.statements[0])
        assert project is None
        assert "projects.id = 'project-1'" in statement
        assert "projects.user_id = 'other-user'" in statement
        assert "FOR SHARE" in postgres_statement

    asyncio.run(scenario())


def test_create_flushes_and_maps_case_insensitive_name_conflict():
    async def scenario():
        project = Project(user_id="user-1", name="Alpha")
        fake = _FakeDBSession()
        created = await DBProjectRepository(fake).create(project)

        assert created == project
        assert fake.flush_count == 1
        assert fake.added[0].name == "Alpha"

        conflict = IntegrityError("insert", {}, RuntimeError("unique"))
        conflict_fake = _FakeDBSession(flush_error=conflict)
        with pytest.raises(ProjectNameConflictError):
            await DBProjectRepository(conflict_fake).create(
                Project(user_id="user-1", name="alpha")
            )

    asyncio.run(scenario())


def test_rename_is_scoped_and_reports_missing_or_duplicate():
    async def scenario():
        record = _record()
        fake = _FakeDBSession(_Result(scalar=record))
        renamed = await DBProjectRepository(fake).rename(
            "project-1",
            "user-1",
            "Renamed",
        )

        statement = _sql(fake.statements[0])
        assert renamed.name == "Renamed"
        assert record.name == "Renamed"
        assert "projects.user_id = 'user-1'" in statement
        assert "FOR UPDATE" in statement

        missing = _FakeDBSession(_Result(scalar=None))
        with pytest.raises(ProjectNotFoundError):
            await DBProjectRepository(missing).rename(
                "project-1",
                "other-user",
                "Hidden",
            )

        conflict = _FakeDBSession(
            _Result(scalar=_record()),
            flush_error=IntegrityError("update", {}, RuntimeError("unique")),
        )
        with pytest.raises(ProjectNameConflictError):
            await DBProjectRepository(conflict).rename(
                "project-1",
                "user-1",
                "alpha",
            )

    asyncio.run(scenario())


def test_delete_is_user_scoped_and_reports_missing():
    async def scenario():
        fake = _FakeDBSession(_Result(rowcount=1))
        await DBProjectRepository(fake).delete("project-1", "user-1")

        statement = _sql(fake.statements[0])
        assert statement.startswith("DELETE FROM projects")
        assert "projects.id = 'project-1'" in statement
        assert "projects.user_id = 'user-1'" in statement

        missing = _FakeDBSession(_Result(rowcount=0))
        with pytest.raises(ProjectNotFoundError):
            await DBProjectRepository(missing).delete("project-1", "other-user")

    asyncio.run(scenario())
