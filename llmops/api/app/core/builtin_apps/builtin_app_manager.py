from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.builtin_apps.entities import BuiltinAppEntity, CategoryEntity


class BuiltinAppManager(BaseModel):
    builtin_app_map: dict[str, BuiltinAppEntity] = Field(default_factory=dict)
    categories: list[CategoryEntity] = Field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_categories()
        self._init_builtin_app_map()

    def get_builtin_app(self, builtin_app_id: str) -> BuiltinAppEntity | None:
        return self.builtin_app_map.get(builtin_app_id)

    def get_builtin_apps(self) -> list[BuiltinAppEntity]:
        return list(self.builtin_app_map.values())

    def get_categories(self) -> list[CategoryEntity]:
        return self.categories

    def _init_builtin_app_map(self) -> None:
        if self.builtin_app_map:
            return
        builtin_apps_path = Path(__file__).resolve().parent / "builtin_apps"
        for yaml_path in sorted(builtin_apps_path.glob("*.y*ml")):
            with yaml_path.open(encoding="utf-8") as f:
                builtin_app = yaml.safe_load(f) or {}
            builtin_app["language_model_config"] = builtin_app.pop("model_config", {})
            entity = BuiltinAppEntity(**builtin_app)
            self.builtin_app_map[entity.id] = entity

    def _init_categories(self) -> None:
        if self.categories:
            return
        categories_path = Path(__file__).resolve().parent / "categories" / "categories.yaml"
        with categories_path.open(encoding="utf-8") as f:
            categories = yaml.safe_load(f) or []
        self.categories = [CategoryEntity(**category) for category in categories]
