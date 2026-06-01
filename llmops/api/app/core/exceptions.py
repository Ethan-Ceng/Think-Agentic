from typing import Any

from app.shared.response import HttpCode


class CustomException(Exception):
    code: HttpCode = HttpCode.FAIL

    def __init__(self, message: str | None = None, data: Any = None):
        super().__init__(message)
        self.message = message or ""
        self.data = data if data is not None else {}


class FailException(CustomException):
    pass


class NotFoundException(CustomException):
    code = HttpCode.NOT_FOUND


class UnauthorizedException(CustomException):
    code = HttpCode.UNAUTHORIZED


class ForbiddenException(CustomException):
    code = HttpCode.FORBIDDEN


class ValidateErrorException(CustomException):
    code = HttpCode.VALIDATE_ERROR

