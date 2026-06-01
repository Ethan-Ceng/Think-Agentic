import base64
import os

import pytest

from app.shared.password import compare_password, hash_password, validate_password


def test_hash_and_compare_password_are_legacy_compatible() -> None:
    salt = os.urandom(16)
    hashed = hash_password("abc12345", salt)

    assert compare_password("abc12345", base64.b64encode(hashed), base64.b64encode(salt))
    assert not compare_password("wrong123", base64.b64encode(hashed), base64.b64encode(salt))


def test_validate_password_requires_letter_number_and_length() -> None:
    validate_password("abc12345")

    with pytest.raises(ValueError):
        validate_password("abcdefgh")

