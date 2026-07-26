#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Project CRUD request and response contracts."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _ProjectNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class CreateProjectRequest(_ProjectNameRequest):
    """Create one user-owned, single-level Project."""


class RenameProjectRequest(_ProjectNameRequest):
    """Rename one user-owned Project."""


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
