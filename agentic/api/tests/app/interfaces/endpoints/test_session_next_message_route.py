from app.main import app
from app.schemas.session import QueueNextMessageRequest


def test_next_message_request_trims_content():
    request = QueueNextMessageRequest(message="  follow up  ")
    assert request.message == "follow up"


def test_next_message_routes_are_registered():
    routes = {
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    path = "/api/sessions/{session_id}/next-message"
    assert (path, "PUT") in routes
    assert (path, "DELETE") in routes
    assert (f"{path}/run", "POST") in routes

