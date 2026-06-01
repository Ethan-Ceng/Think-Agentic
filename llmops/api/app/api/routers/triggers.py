from fastapi import APIRouter

router = APIRouter(prefix="/triggers", tags=["triggers"])


@router.get("/status")
async def triggers_status() -> dict[str, str]:
    return {"status": "ok"}
