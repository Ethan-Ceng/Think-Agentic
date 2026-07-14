import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.schemas.exceptions import BadRequestError


ENCRYPTED_PREFIX = "enc:"


class ConfigCrypto:
    def __init__(self) -> None:
        settings = get_settings()
        raw_key = settings.config_encryption_key
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        if not value or value.startswith(ENCRYPTED_PREFIX):
            return value
        token = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"{ENCRYPTED_PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        if not value or not value.startswith(ENCRYPTED_PREFIX):
            return value
        try:
            token = value[len(ENCRYPTED_PREFIX) :].encode("utf-8")
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            raise BadRequestError("存储密钥无法解密，请检查 CONFIG_ENCRYPTION_KEY") from exc
