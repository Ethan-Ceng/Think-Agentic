import pytest
from pydantic import ValidationError

from app.core.entities.event import InteractionDecision
from app.main import app
from app.schemas.session import ResolveInteractionRequest


def test_interaction_resolve_route_is_registered() -> None:
    matching = [
        route
        for route in app.routes
        if getattr(route, "path", "")
        == "/api/sessions/{session_id}/interactions/{action_id}/resolve"
    ]
    assert len(matching) == 1
    assert "POST" in matching[0].methods


def test_interaction_resolve_request_rejects_duplicate_or_oversized_values() -> None:
    valid = ResolveInteractionRequest(
        decision=InteractionDecision.ANSWER,
        selected_values=["staging"],
    )
    assert valid.selected_values == ["staging"]

    with pytest.raises(ValidationError):
        ResolveInteractionRequest(
            decision=InteractionDecision.ANSWER,
            selected_values=["staging", "staging"],
        )
    with pytest.raises(ValidationError):
        ResolveInteractionRequest(
            decision=InteractionDecision.ANSWER,
            answer="x" * 10001,
        )
