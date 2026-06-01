from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.exceptions import NotFoundException, ValidateErrorException


def test_custom_exception_handler_keeps_legacy_payload_shape() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundException("missing")

    response = TestClient(app).get("/missing")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "missing", "data": {}}


def test_custom_exception_handler_keeps_exception_data() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/invalid")
    def invalid() -> None:
        raise ValidateErrorException("invalid", data={"field": ["required"]})

    response = TestClient(app).get("/invalid")

    assert response.status_code == 422
    assert response.json() == {"code": "validate_error", "message": "invalid", "data": {"field": ["required"]}}

