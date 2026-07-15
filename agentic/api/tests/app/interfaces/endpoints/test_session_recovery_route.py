#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas import session as session_schemas


def test_resume_request_accepts_only_supported_modes() -> None:
    ResumeSessionRequest = session_schemas.ResumeSessionRequest
    assert ResumeSessionRequest(mode="continue").mode == "continue"
    assert ResumeSessionRequest(mode="restart").mode == "restart"
    with pytest.raises(ValidationError):
        ResumeSessionRequest(mode="automatic")


def test_resume_sse_route_is_registered() -> None:
    matching = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/sessions/{session_id}/resume"
    ]

    assert len(matching) == 1
    assert "POST" in matching[0].methods
