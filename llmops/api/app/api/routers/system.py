from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/ping", operation_id="system_ping")
async def ping() -> dict:
    return {"code": "success", "message": "", "data": {"pong": "success"}}


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readyz() -> HealthResponse:
    return HealthResponse(status="ok")
