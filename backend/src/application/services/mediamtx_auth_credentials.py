"""Map MediaMTX authHTTP JSON to username/password (incl. RTMP query params)."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs


def resolve_mediamtx_auth_fields(body: dict[str, Any]) -> tuple[str, str, str, str]:
    """Extract user, password, path, action from a MediaMTX authHTTP POST body."""
    user = str(body.get("user") or "").strip()
    pwd = str(body.get("password") or "")
    path = str(body.get("path") or "")
    action = str(body.get("action") or "")
    query = str(body.get("query") or "").strip()
    if not query:
        return user, pwd, path, action

    parsed = parse_qs(query, keep_blank_values=True)

    def _first(*keys: str) -> str:
        for key in keys:
            values = parsed.get(key)
            if values and values[0]:
                return values[0]
        return ""

    if not user:
        user = _first("user", "username").strip()
    if not pwd:
        pwd = _first("pass", "password", "pwd")
    return user, pwd, path, action
