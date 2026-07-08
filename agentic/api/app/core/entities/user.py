#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""User domain entity."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """Application user."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str = ""
    avatar: str = ""
    password_hash: str = ""
    password_salt: str = ""
    password_algorithm: str = "pbkdf2_sha256"
    status: str = "active"
    last_login_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
