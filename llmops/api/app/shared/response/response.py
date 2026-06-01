from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse, StreamingResponse

from .http_code import HttpCode


@dataclass
class Response:
    """Legacy-compatible HTTP response payload."""

    code: HttpCode = HttpCode.SUCCESS
    message: str = ""
    data: Any = field(default_factory=dict)


def json(data: Response | None = None) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(data), status_code=200)


def success_json(data: Any = None) -> JSONResponse:
    return json(Response(code=HttpCode.SUCCESS, message="", data=data))


def fail_json(data: Any = None) -> JSONResponse:
    return json(Response(code=HttpCode.FAIL, message="", data=data))


def validate_error_json(errors: dict[str, Any] | None = None) -> JSONResponse:
    errors = errors or {}
    first_key = next(iter(errors), None)
    msg = errors.get(first_key, [""])[0] if first_key is not None else ""
    return json(Response(code=HttpCode.VALIDATE_ERROR, message=msg, data=errors))


def message(code: HttpCode | None = None, msg: str = "") -> JSONResponse:
    return json(Response(code=code or HttpCode.SUCCESS, message=msg, data={}))


def success_message(msg: str = "") -> JSONResponse:
    return message(code=HttpCode.SUCCESS, msg=msg)


def fail_message(msg: str = "") -> JSONResponse:
    return message(code=HttpCode.FAIL, msg=msg)


def not_found_message(msg: str = "") -> JSONResponse:
    return message(code=HttpCode.NOT_FOUND, msg=msg)


def unauthorized_message(msg: str = "") -> JSONResponse:
    return message(code=HttpCode.UNAUTHORIZED, msg=msg)


def forbidden_message(msg: str = "") -> JSONResponse:
    return message(code=HttpCode.FORBIDDEN, msg=msg)


def compact_generate_response(response: Response | Generator[str, None, None]) -> JSONResponse | StreamingResponse:
    if isinstance(response, Response):
        return json(response)

    def generate() -> Generator[str, None, None]:
        yield from response

    return StreamingResponse(generate(), status_code=200, media_type="text/event-stream")

