#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""User-scoped configuration entity."""
import uuid
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field


class Config(BaseModel):
    """A single typed configuration document owned by one user."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    config_type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "config_v1"
    updated_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
