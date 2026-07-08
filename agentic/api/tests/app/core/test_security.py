import time

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  User@Example.COM ") == "user@example.com"


def test_password_validation_requires_letter_digit_and_length() -> None:
    assert validate_password("abc12345")
    assert not validate_password("abcdefgh")
    assert not validate_password("12345678")
    assert not validate_password("a1")


def test_password_hash_roundtrip() -> None:
    password_hash, password_salt = hash_password("abc12345")

    assert verify_password("abc12345", password_hash, password_salt)
    assert not verify_password("wrong123", password_hash, password_salt)


def test_access_token_roundtrip_and_expiration() -> None:
    token = create_access_token("user-1", "secret", ttl_seconds=60)
    payload = decode_access_token(token, "secret")

    assert payload is not None
    assert payload["sub"] == "user-1"
    assert decode_access_token(token, "other-secret") is None

    expired = create_access_token("user-1", "secret", ttl_seconds=-1)
    time.sleep(1)
    assert decode_access_token(expired, "secret") is None
