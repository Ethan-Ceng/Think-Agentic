#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Config repository protocol."""
from typing import List, Optional, Protocol

from app.core.entities.config import Config


class ConfigRepository(Protocol):
    """User-scoped config repository protocol."""

    async def save(self, config: Config) -> None:
        ...

    async def get_by_user_and_type(self, user_id: str, config_type: str) -> Optional[Config]:
        ...

    async def get_all_by_user(self, user_id: str) -> List[Config]:
        ...
