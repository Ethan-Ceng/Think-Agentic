from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["web"])


@router.get("/status")
async def web_status() -> dict[str, str]:
    return {"status": "ok"}
