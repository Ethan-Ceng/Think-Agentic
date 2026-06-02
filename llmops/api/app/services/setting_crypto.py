import base64
import hashlib
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings
from app.core.exceptions import FailException

ENCRYPTED_PREFIX = "enc:"
MASKED_SECRET = "********"


@dataclass
class SettingCrypto:
    settings: Settings = field(default_factory=get_settings)

    def encrypt(self, value: str) -> str:
        if not value or value.startswith(ENCRYPTED_PREFIX) or value == MASKED_SECRET:
            return value
        token = self._fernet().encrypt(value.encode("utf-8")).decode("utf-8")
        return f"{ENCRYPTED_PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        if not value or not value.startswith(ENCRYPTED_PREFIX):
            return value
        try:
            return self._fernet().decrypt(value[len(ENCRYPTED_PREFIX) :].encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise FailException("Setting secret cannot be decrypted") from exc

    def mask(self, value: str) -> str:
        return MASKED_SECRET if value else ""

    def _fernet(self) -> Fernet:
        raw_key = self.settings.setting_crypto_key or self.settings.jwt_secret_key
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
