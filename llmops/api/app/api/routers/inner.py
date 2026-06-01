from fastapi import APIRouter

router = APIRouter(prefix="/inner/api", tags=["inner"])


@router.get("/status")
async def inner_status() -> dict[str, str]:
    return {"status": "ok"}
