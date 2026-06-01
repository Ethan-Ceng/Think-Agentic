from enum import StrEnum


class HttpCode(StrEnum):
    """Business response code compatible with the legacy api package."""

    SUCCESS = "success"
    FAIL = "fail"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    VALIDATE_ERROR = "validate_error"
