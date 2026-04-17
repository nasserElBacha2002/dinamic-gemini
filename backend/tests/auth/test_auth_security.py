from datetime import datetime, timezone

import jwt
from passlib.context import CryptContext

from src.auth.security import create_access_token, decode_access_token, verify_password

_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def test_verify_password_valid_and_invalid():
    # Use passlib hash format via verify_password behavior; invalid hashes should fail closed.
    h = _PWD_CONTEXT.hash("pw")
    assert verify_password("pw", h) is True
    assert verify_password("wrong", h) is False
    assert verify_password("", "") is False
    assert verify_password("pw", "") is False


def test_token_roundtrip_and_expiration():
    secret = "s" * 40
    token = create_access_token(
        "admin",
        username="admin",
        role="administrator",
        secret=secret,
        expires_minutes=5,
        now=datetime.now(timezone.utc),
    )
    payload = decode_access_token(token, secret=secret)
    assert payload["sub"] == "admin"
    assert payload["principal_id"] == "admin"
    assert payload["username"] == "admin"
    assert payload["role"] == "administrator"

    expired = create_access_token(
        "admin",
        username="admin",
        role="administrator",
        secret=secret,
        expires_minutes=1,
        now=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    try:
        decode_access_token(expired, secret=secret)
        assert False, "expected ExpiredSignatureError"
    except jwt.ExpiredSignatureError:
        pass

