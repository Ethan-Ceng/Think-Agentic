from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["service_api"])


@router.get("/status")
async def service_api_status() -> dict[str, str]:
    return {"status": "ok"}
