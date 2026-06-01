import base64
import binascii
import hashlib
import re
from typing import Any

password_pattern = r"^(?=.*[a-zA-Z])(?=.*\d).{8,16}$"


def validate_password(password: str, pattern: str = password_pattern) -> None:
    if re.match(pattern, password) is None:
        raise ValueError("Password must contain at least one letter and one number, length 8-16")


def hash_password(password: str, salt: Any) -> bytes:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 10000)
    return binascii.hexlify(dk)


def compare_password(password: str, password_hashed_base64: Any, salt_base64: Any) -> bool:
    return hash_password(password, base64.b64decode(salt_base64)) == base64.b64decode(password_hashed_base64)

