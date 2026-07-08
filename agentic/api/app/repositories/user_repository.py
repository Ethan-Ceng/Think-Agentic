#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""User repository protocol."""
from typing import Optional, Protocol

from app.core.entities.user import User


class UserRepository(Protocol):
    """User repository protocol."""

    async def save(self, user: User) -> None:
        ...

    async def get_by_id(self, user_id: str) -> Optional[User]:
        ...

    async def get_by_email(self, email: str) -> Optional[User]:
        ...
