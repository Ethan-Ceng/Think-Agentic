#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Single-level Project directory domain model."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectNotFoundError(LookupError):
    """The Project does not exist or is not visible to the current user."""


class ProjectNameConflictError(RuntimeError):
    """The user already owns a Project with the same case-insensitive name."""


class Project(BaseModel):
    """A single-level directory used only to organize one user's Sessions."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
