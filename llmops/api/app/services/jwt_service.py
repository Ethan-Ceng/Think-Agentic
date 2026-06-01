from dataclasses import dataclass
from typing import Any

from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import Settings
from app.core.exceptions import UnauthorizedException


@dataclass
class JwtService:
    settings: Settings

    def _get_secret_key(self) -> str:
        secret_key = self.settings.jwt_secret_key
        if len(secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
        return secret_key

    def generate_token(self, payload: dict[str, Any]) -> str:
        return jwt.encode(payload, self._get_secret_key(), algorithm="HS256")

    def parse_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self._get_secret_key(), algorithms=["HS256"])
        except ExpiredSignatureError as exc:
            raise UnauthorizedException("Authorization credential expired, please login again") from exc
        except JWTError as exc:
            raise UnauthorizedException("Invalid token, please login again") from exc
        except Exception as exc:
            raise UnauthorizedException(str(exc)) from exc

