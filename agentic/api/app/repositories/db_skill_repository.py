from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities.skill import (
    RunSkill,
    Skill,
    SkillInstallation,
    SkillScope,
    SkillStatus,
    SkillVersion,
)
from app.models import (
    AgentRunModel,
    RunSkillModel,
    SkillInstallationModel,
    SkillModel,
    SkillVersionModel,
)
from app.repositories.skill_repository import SkillRepository


class DBSkillRepository(SkillRepository):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def save_skill(self, skill: Skill) -> None:
        record = await self.db_session.get(SkillModel, skill.id)
        if record is None:
            self.db_session.add(SkillModel.from_domain(skill))
            # The publish flow follows this insert with Core UPDATE statements.
            # AsyncSession does not guarantee an autoflush before those statements,
            # so make the parent row visible before creating its version/pointer.
            await self.db_session.flush()
            return
        raise ValueError(f"Skill {skill.id} already exists")

    async def get_personal_by_id(self, user_id: str, skill_id: str) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.owner_user_id == user_id,
            SkillModel.scope == SkillScope.PERSONAL,
            SkillModel.status != SkillStatus.ARCHIVED,
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def list_personal(self, user_id: str) -> list[Skill]:
        stmt = (
            select(SkillModel)
            .where(
                SkillModel.owner_user_id == user_id,
                SkillModel.scope == SkillScope.PERSONAL,
                SkillModel.status != SkillStatus.ARCHIVED,
            )
            .order_by(SkillModel.created_at.asc(), SkillModel.id.asc())
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def update_personal(
        self,
        user_id: str,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        auto_invoke: bool | None = None,
        current_version_id: str | None = None,
    ) -> bool:
        values = {
            key: value
            for key, value in {
                "display_name": display_name,
                "description": description,
                "enabled": enabled,
                "auto_invoke": auto_invoke,
                "current_version_id": current_version_id,
            }.items()
            if value is not None
        }
        if not values:
            return False
        stmt = (
            update(SkillModel)
            .where(
                SkillModel.id == skill_id,
                SkillModel.owner_user_id == user_id,
                SkillModel.scope == SkillScope.PERSONAL,
                SkillModel.status != SkillStatus.ARCHIVED,
            )
            .values(**values)
        )
        result = await self.db_session.execute(stmt)
        return bool(result.rowcount)

    async def archive_personal(self, user_id: str, skill_id: str) -> bool:
        stmt = (
            update(SkillModel)
            .where(
                SkillModel.id == skill_id,
                SkillModel.owner_user_id == user_id,
                SkillModel.scope == SkillScope.PERSONAL,
                SkillModel.status != SkillStatus.ARCHIVED,
            )
            .values(status=SkillStatus.ARCHIVED, enabled=False, auto_invoke=False)
        )
        result = await self.db_session.execute(stmt)
        return bool(result.rowcount)

    async def list_marketplace(self) -> list[Skill]:
        stmt = (
            select(SkillModel)
            .where(
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
            )
            .order_by(SkillModel.created_at.asc(), SkillModel.id.asc())
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def get_marketplace_by_id(self, skill_id: str) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.scope == SkillScope.MARKETPLACE,
            SkillModel.status == SkillStatus.ACTIVE,
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def update_marketplace(
        self,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        current_version_id: str | None = None,
    ) -> bool:
        values = {
            key: value
            for key, value in {
                "display_name": display_name,
                "description": description,
                "current_version_id": current_version_id,
            }.items()
            if value is not None
        }
        if not values:
            return False
        result = await self.db_session.execute(
            update(SkillModel)
            .where(
                SkillModel.id == skill_id,
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
            )
            .values(**values)
        )
        return bool(result.rowcount)

    async def save_version(self, version: SkillVersion) -> None:
        record = await self.db_session.get(SkillVersionModel, version.id)
        if record is None:
            self.db_session.add(SkillVersionModel.from_domain(version))
            # current_version_id is updated with a Core UPDATE immediately after
            # this call and references this row through a foreign key.
            await self.db_session.flush()

    async def get_personal_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None:
        stmt = (
            select(SkillVersionModel)
            .join(SkillModel, SkillModel.id == SkillVersionModel.skill_id)
            .where(
                SkillVersionModel.id == version_id,
                SkillModel.owner_user_id == user_id,
                SkillModel.scope == SkillScope.PERSONAL,
            )
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def get_marketplace_version(
        self, version_id: str
    ) -> SkillVersion | None:
        stmt = (
            select(SkillVersionModel)
            .join(SkillModel, SkillModel.id == SkillVersionModel.skill_id)
            .where(
                SkillVersionModel.id == version_id,
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
            )
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def list_marketplace_versions(self, skill_id: str) -> list[SkillVersion]:
        stmt = (
            select(SkillVersionModel)
            .join(SkillModel, SkillModel.id == SkillVersionModel.skill_id)
            .where(
                SkillVersionModel.skill_id == skill_id,
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
            )
            .order_by(SkillVersionModel.version.asc())
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def save_installation(self, installation: SkillInstallation) -> None:
        skill = await self.db_session.get(SkillModel, installation.skill_id)
        if skill is None or skill.scope != SkillScope.MARKETPLACE:
            raise ValueError("Only marketplace Skills can be installed")
        version = await self.db_session.get(
            SkillVersionModel, installation.pinned_version_id
        )
        if version is None or version.skill_id != installation.skill_id:
            raise ValueError("Pinned version does not belong to the installed Skill")
        stmt = select(SkillInstallationModel).where(
            SkillInstallationModel.user_id == installation.user_id,
            SkillInstallationModel.skill_id == installation.skill_id,
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        if record is None:
            self.db_session.add(SkillInstallationModel.from_domain(installation))
            return
        for field, value in installation.model_dump(mode="python").items():
            if field not in {"id", "installed_at"}:
                setattr(record, field, value)

    async def get_installation(
        self, user_id: str, skill_id: str
    ) -> SkillInstallation | None:
        stmt = select(SkillInstallationModel).where(
            SkillInstallationModel.user_id == user_id,
            SkillInstallationModel.skill_id == skill_id,
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def list_installed_marketplace(
        self, user_id: str
    ) -> list[SkillInstallation]:
        stmt = (
            select(SkillInstallationModel)
            .join(SkillModel, SkillModel.id == SkillInstallationModel.skill_id)
            .where(
                SkillInstallationModel.user_id == user_id,
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
            )
            .order_by(
                SkillInstallationModel.installed_at.asc(),
                SkillInstallationModel.id.asc(),
            )
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]

    async def get_installed_marketplace_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None:
        stmt = (
            select(SkillVersionModel)
            .join(
                SkillInstallationModel,
                SkillInstallationModel.pinned_version_id == SkillVersionModel.id,
            )
            .join(SkillModel, SkillModel.id == SkillInstallationModel.skill_id)
            .where(
                SkillVersionModel.id == version_id,
                SkillInstallationModel.user_id == user_id,
                SkillInstallationModel.enabled.is_(True),
                SkillModel.scope == SkillScope.MARKETPLACE,
                SkillModel.status == SkillStatus.ACTIVE,
                SkillModel.enabled.is_(True),
            )
        )
        record = (await self.db_session.execute(stmt)).scalar_one_or_none()
        return record.to_domain() if record is not None else None

    async def delete_installation(self, user_id: str, skill_id: str) -> bool:
        stmt = delete(SkillInstallationModel).where(
            SkillInstallationModel.user_id == user_id,
            SkillInstallationModel.skill_id == skill_id,
        )
        result = await self.db_session.execute(stmt)
        return bool(result.rowcount)

    async def save_run_skill(self, run_skill: RunSkill) -> None:
        self.db_session.add(RunSkillModel.from_domain(run_skill))

    async def list_run_skills_for_user(
        self, user_id: str, run_id: str
    ) -> list[RunSkill]:
        stmt = (
            select(RunSkillModel)
            .join(AgentRunModel, AgentRunModel.id == RunSkillModel.run_id)
            .where(AgentRunModel.user_id == user_id, RunSkillModel.run_id == run_id)
            .order_by(RunSkillModel.created_at.asc(), RunSkillModel.id.asc())
        )
        records = (await self.db_session.execute(stmt)).scalars().all()
        return [record.to_domain() for record in records]
