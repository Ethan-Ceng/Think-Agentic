import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.entities.skill import (
    RunSkill,
    Skill,
    SkillInstallation,
    SkillScope,
    SkillSelectionMode,
    SkillSource,
    SkillVersion,
)
from app.models import (
    AgentRunModel,
    SessionModel,
    SkillInstallationModel,
    SkillModel,
    SkillVersionModel,
    UserModel,
)
from app.repositories.db_skill_repository import DBSkillRepository
from app.repositories.db_uow import DBUnitOfWork


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_settings().sqlalchemy_database_uri)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        transaction = await session.begin()
        try:
            yield session
        finally:
            await transaction.rollback()
    await engine.dispose()


async def add_user(session: AsyncSession, label: str) -> str:
    user_id = str(uuid.uuid4())
    session.add(
        UserModel(
            id=user_id,
            email=f"{label}-{user_id}@example.com",
            name=label,
        )
    )
    await session.flush()
    return user_id


def personal_skill(user_id: str, name: str = "report-writer") -> Skill:
    return Skill(
        owner_user_id=user_id,
        name=name,
        display_name="Report Writer",
        description="Create evidence-based reports for structured research requests.",
        scope=SkillScope.PERSONAL,
    )


def marketplace_skill(name: str = "market-research") -> Skill:
    return Skill(
        name=name,
        display_name="Market Research",
        description="Research markets using an evidence-first runbook.",
        scope=SkillScope.MARKETPLACE,
    )


def published_version(skill_id: str, created_by_user_id: str | None) -> SkillVersion:
    return SkillVersion(
        skill_id=skill_id,
        version=1,
        manifest={
            "name": "market-research",
            "description": "Research markets using an evidence-first runbook.",
        },
        storage_provider="local",
        storage_key=f"skills/{skill_id}/1.skill",
        storage_config={"root": "skills"},
        package_sha256="a" * 64,
        package_size=1024,
        file_count=2,
        status="published",
        created_by_user_id=created_by_user_id,
    )


@pytest.mark.anyio
async def test_personal_skill_queries_and_mutations_are_user_scoped(
    db_session: AsyncSession,
) -> None:
    user_a = await add_user(db_session, "user-a")
    user_b = await add_user(db_session, "user-b")
    repo = DBSkillRepository(db_session)
    skill_a = personal_skill(user_a)
    skill_b = personal_skill(user_b)
    await repo.save_skill(skill_a)
    await repo.save_skill(skill_b)
    await db_session.flush()

    assert [skill.id for skill in await repo.list_personal(user_a)] == [skill_a.id]
    assert [skill.id for skill in await repo.list_personal(user_b)] == [skill_b.id]
    assert await repo.get_personal_by_id(user_b, skill_a.id) is None

    assert not await repo.update_personal(
        user_b,
        skill_a.id,
        display_name="Cross-user update",
    )
    assert not await repo.archive_personal(user_b, skill_a.id)

    unchanged = await repo.get_personal_by_id(user_a, skill_a.id)
    assert unchanged is not None
    assert unchanged.display_name == "Report Writer"
    assert unchanged.status == "active"

    assert await repo.update_personal(
        user_a,
        skill_a.id,
        display_name="Updated Report Writer",
        auto_invoke=False,
    )
    updated = await repo.get_personal_by_id(user_a, skill_a.id)
    assert updated is not None
    assert updated.display_name == "Updated Report Writer"
    assert not updated.auto_invoke

    assert await repo.archive_personal(user_a, skill_a.id)
    assert await repo.get_personal_by_id(user_a, skill_a.id) is None


@pytest.mark.anyio
async def test_save_skill_cannot_overwrite_an_existing_owner_scoped_record(
    db_session: AsyncSession,
) -> None:
    user_a = await add_user(db_session, "user-a")
    user_b = await add_user(db_session, "user-b")
    repo = DBSkillRepository(db_session)
    skill = personal_skill(user_a)
    await repo.save_skill(skill)
    await db_session.flush()

    forged = skill.model_copy(
        update={"owner_user_id": user_b, "display_name": "Forged ownership"}
    )
    with pytest.raises(ValueError, match="already exists"):
        await repo.save_skill(forged)

    stored = await repo.get_personal_by_id(user_a, skill.id)
    assert stored is not None
    assert stored.display_name == "Report Writer"
    assert await repo.get_personal_by_id(user_b, skill.id) is None


@pytest.mark.anyio
async def test_marketplace_is_global_but_installations_are_user_scoped(
    db_session: AsyncSession,
) -> None:
    user_a = await add_user(db_session, "user-a")
    user_b = await add_user(db_session, "user-b")
    repo = DBSkillRepository(db_session)
    market_skill = marketplace_skill()
    await repo.save_skill(market_skill)
    version = published_version(market_skill.id, None)
    await repo.save_version(version)
    await db_session.flush()

    assert [skill.id for skill in await repo.list_marketplace()] == [market_skill.id]
    assert await repo.list_installed_marketplace(user_a) == []
    assert await repo.list_installed_marketplace(user_b) == []

    await repo.save_installation(
        SkillInstallation(
            user_id=user_a,
            skill_id=market_skill.id,
            pinned_version_id=version.id,
        )
    )
    await db_session.flush()

    installed_a = await repo.list_installed_marketplace(user_a)
    assert [installation.skill_id for installation in installed_a] == [
        market_skill.id
    ]
    assert await repo.list_installed_marketplace(user_b) == []
    assert (
        await repo.get_installed_marketplace_version(user_b, version.id) is None
    )
    assert (
        await repo.get_installed_marketplace_version(user_a, version.id)
    ) == version
    assert await repo.get_marketplace_version(version.id) == version
    assert await repo.get_installation(user_b, market_skill.id) is None
    assert await repo.get_installation(user_a, market_skill.id) is not None

    replacement = SkillInstallation(
        user_id=user_a,
        skill_id=market_skill.id,
        pinned_version_id=version.id,
        enabled=False,
        auto_invoke=False,
    )
    await repo.save_installation(replacement)
    await db_session.flush()
    updated_installation = await repo.get_installation(user_a, market_skill.id)
    assert updated_installation is not None
    assert not updated_installation.enabled
    assert not updated_installation.auto_invoke
    assert not await repo.delete_installation(user_b, market_skill.id)
    assert await repo.delete_installation(user_a, market_skill.id)
    assert await repo.get_installation(user_a, market_skill.id) is None


@pytest.mark.anyio
async def test_personal_version_lookup_is_owner_scoped_and_versions_are_immutable(
    db_session: AsyncSession,
) -> None:
    user_a = await add_user(db_session, "user-a")
    user_b = await add_user(db_session, "user-b")
    repo = DBSkillRepository(db_session)
    skill = personal_skill(user_a)
    await repo.save_skill(skill)
    version = published_version(skill.id, user_a)
    await repo.save_version(version)
    await db_session.flush()

    assert await repo.get_personal_version(user_a, version.id) == version
    assert await repo.get_personal_version(user_b, version.id) is None

    changed = version.model_copy(update={"storage_key": "forged/changed.skill"})
    await repo.save_version(changed)
    await db_session.flush()
    assert await repo.get_personal_version(user_a, version.id) == version


@pytest.mark.anyio
async def test_installation_rejects_personal_skills_and_mismatched_versions(
    db_session: AsyncSession,
) -> None:
    user_id = await add_user(db_session, "user")
    repo = DBSkillRepository(db_session)
    personal = personal_skill(user_id)
    market_a = marketplace_skill("market-a")
    market_b = marketplace_skill("market-b")
    await repo.save_skill(personal)
    await repo.save_skill(market_a)
    await repo.save_skill(market_b)
    personal_version = published_version(personal.id, user_id)
    market_a_version = published_version(market_a.id, None)
    await repo.save_version(personal_version)
    await repo.save_version(market_a_version)
    await db_session.flush()

    with pytest.raises(ValueError, match="marketplace"):
        await repo.save_installation(
            SkillInstallation(
                user_id=user_id,
                skill_id=personal.id,
                pinned_version_id=personal_version.id,
            )
        )

    with pytest.raises(ValueError, match="does not belong"):
        await repo.save_installation(
            SkillInstallation(
                user_id=user_id,
                skill_id=market_b.id,
                pinned_version_id=market_a_version.id,
            )
        )


@pytest.mark.anyio
async def test_run_skill_history_is_scoped_through_run_owner(
    db_session: AsyncSession,
) -> None:
    user_a = await add_user(db_session, "user-a")
    user_b = await add_user(db_session, "user-b")
    session_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    db_session.add(SessionModel(id=session_id, user_id=user_a, title="Skill run"))
    await db_session.flush()
    db_session.add(
        AgentRunModel(
            id=run_id,
            trace_id=str(uuid.uuid4()),
            user_id=user_a,
            session_id=session_id,
        )
    )
    await db_session.flush()
    repo = DBSkillRepository(db_session)
    run_skill = RunSkill(
        run_id=run_id,
        name="skill-creator",
        source=SkillSource.BUNDLED,
        selection_mode=SkillSelectionMode.MANUAL,
        content_sha256="b" * 64,
        reason="The user selected the bundled Skill.",
        sandbox_path=f"/home/ubuntu/.agentic/skills/{run_id}/skill-creator",
    )
    await repo.save_run_skill(run_skill)
    await db_session.flush()

    assert await repo.list_run_skills_for_user(user_a, run_id) == [run_skill]
    assert await repo.list_run_skills_for_user(user_b, run_id) == []


def test_skill_models_declare_required_database_constraints() -> None:
    skill_indexes = {index.name for index in SkillModel.__table__.indexes}
    skill_constraints = {
        constraint.name for constraint in SkillModel.__table__.constraints
    }
    installation_constraints = {
        constraint.name for constraint in SkillInstallationModel.__table__.constraints
    }
    version_constraints = {
        constraint.name for constraint in SkillVersionModel.__table__.constraints
    }

    assert "ux_skills_personal_owner_name_active" in skill_indexes
    assert "ux_skills_marketplace_name_active" in skill_indexes
    assert "ck_skills_scope_owner" in skill_constraints
    assert "uq_skill_installations_user_skill" in installation_constraints
    assert "uq_skill_versions_skill_version" in version_constraints


@pytest.mark.anyio
async def test_database_uow_exposes_skill_repository() -> None:
    engine = create_async_engine(get_settings().sqlalchemy_database_uri)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    uow = DBUnitOfWork(session_factory)

    entered = await uow.__aenter__()
    try:
        assert isinstance(entered.skill, DBSkillRepository)
    finally:
        assert entered.db_session is not None
        await entered.db_session.close()
        entered.db_session = None
        await engine.dispose()
