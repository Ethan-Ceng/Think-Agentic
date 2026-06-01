from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette import status
from starlette.responses import JSONResponse

from app.core.exceptions import CustomException
from app.shared.response import HttpCode


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "data": {}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CustomException)
    async def handle_custom_error(_: Request, exc: CustomException) -> JSONResponse:
        return JSONResponse(
            status_code=_status_code_for_http_code(exc.code),
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"code": "validation_error", "message": "Request validation failed", "data": exc.errors()},
        )


def _status_code_for_http_code(code: HttpCode) -> int:
    return {
        HttpCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        HttpCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
        HttpCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
        HttpCode.VALIDATE_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    }.get(code, status.HTTP_400_BAD_REQUEST)
