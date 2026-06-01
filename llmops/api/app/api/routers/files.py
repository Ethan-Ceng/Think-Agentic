from fastapi import APIRouter

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/status")
async def files_status() -> dict[str, str]:
    return {"status": "ok"}
