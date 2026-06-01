from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundException
from app.core.tools.builtin_tools.entities import CategoryEntity


class BuiltinCategoryManager(BaseModel):
    category_map: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_categories()

    def get_category_map(self) -> dict[str, Any]:
        return self.category_map

    def _init_categories(self) -> None:
        if self.category_map:
            return

        category_path = Path(__file__).resolve().parent
        with (category_path / "categories.yaml").open(encoding="utf-8") as f:
            categories = yaml.safe_load(f) or []

        for category in categories:
            category_entity = CategoryEntity(**category)
            icon_path = category_path / "icons" / category_entity.icon
            if not icon_path.exists():
                raise NotFoundException(f"Category icon does not exist: {category_entity.category}")

            self.category_map[category_entity.category] = {
                "entity": category_entity,
                "icon": icon_path.read_text(encoding="utf-8"),
            }

