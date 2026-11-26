"""RTMP query param extraction for MediaMTX authHTTP bodies."""

from __future__ import annotations

from src.application.services.mediamtx_auth_credentials import resolve_mediamtx_auth_fields


def test_prefers_explicit_user_and_password() -> None:
    user, pwd, path, action = resolve_mediamtx_auth_fields(
        {
            "user": "nasser",
            "password": "secret",
            "path": "live/a/b",
            "action": "publish",
            "query": "user=other&pass=ignored",
        }
    )
    assert user == "nasser"
    assert pwd == "secret"
    assert path == "live/a/b"
    assert action == "publish"


def test_fills_from_rtmp_query() -> None:
    user, pwd, path, action = resolve_mediamtx_auth_fields(
        {
            "user": "",
            "password": "",
            "path": "live/prueba-26-11/01",
            "action": "publish",
            "query": "user=nasser&pass=Libano02",
        }
    )
    assert user == "nasser"
    assert pwd == "Libano02"
