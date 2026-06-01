from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt

from app.core.config import Settings

ALGORITHM = "HS256"


def create_access_token(subject: str, settings: Settings, extra: dict[str, Any] | None = None) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
