import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.app_factory import create_app
from app.infrastructure.celery import celery_app

app = create_app()

__all__ = ["app", "celery_app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("API_HOST", os.getenv("BACKEND_HOST", "127.0.0.1")),
        port=int(os.getenv("API_PORT", os.getenv("BACKEND_PORT", "5011"))),
        reload=os.getenv("API_RELOAD", os.getenv("BACKEND_RELOAD", "true")).lower() in {"1", "true", "yes"},
    )
