#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Authentication helpers."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any


PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,16}$")
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 120_000


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> bool:
    return bool(PASSWORD_PATTERN.match(password))


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return base64.b64encode(digest).decode("ascii"), password_salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    if not password_hash or not password_salt:
        return False
    candidate_hash, _ = hash_password(password, password_salt)
    return hmac.compare_digest(candidate_hash, password_hash)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(user_id: str, secret_key: str, ttl_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
    }
    signing_input = ".".join(
        [
            _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str, secret_key: str) -> dict[str, Any] | None:
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}"
        expected = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64encode(expected), signature_part):
            return None

        payload = json.loads(_b64decode(payload_part))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
