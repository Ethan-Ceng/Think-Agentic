from typing import Protocol

from app.core.entities.skill import RunSkill, Skill, SkillInstallation, SkillVersion


class SkillRepository(Protocol):
    async def save_skill(self, skill: Skill) -> None: ...

    async def get_personal_by_id(self, user_id: str, skill_id: str) -> Skill | None: ...

    async def list_personal(self, user_id: str) -> list[Skill]: ...

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
    ) -> bool: ...

    async def archive_personal(self, user_id: str, skill_id: str) -> bool: ...

    async def list_marketplace(self) -> list[Skill]: ...

    async def get_marketplace_by_id(self, skill_id: str) -> Skill | None: ...

    async def update_marketplace(
        self,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        current_version_id: str | None = None,
    ) -> bool: ...

    async def save_version(self, version: SkillVersion) -> None: ...

    async def get_personal_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None: ...

    async def get_marketplace_version(
        self, version_id: str
    ) -> SkillVersion | None: ...

    async def list_marketplace_versions(self, skill_id: str) -> list[SkillVersion]: ...

    async def save_installation(self, installation: SkillInstallation) -> None: ...

    async def get_installation(
        self, user_id: str, skill_id: str
    ) -> SkillInstallation | None: ...

    async def list_installed_marketplace(
        self, user_id: str
    ) -> list[SkillInstallation]: ...

    async def get_installed_marketplace_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None: ...

    async def delete_installation(self, user_id: str, skill_id: str) -> bool: ...

    async def save_run_skill(self, run_skill: RunSkill) -> None: ...

    async def list_run_skills_for_user(
        self, user_id: str, run_id: str
    ) -> list[RunSkill]: ...
