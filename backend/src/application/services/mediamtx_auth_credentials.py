"""Map MediaMTX authHTTP JSON to username/password (incl. RTMP query params)."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs


def _merge_query_strings(*parts: str) -> str:
    tokens: list[str] = []
    for part in parts:
        raw = (part or "").strip().lstrip("?&")
        if raw:
            tokens.append(raw)
    return "&".join(tokens)


def _credentials_from_query_string(query: str) -> tuple[str, str]:
    if not query:
        return "", ""
    parsed = parse_qs(query, keep_blank_values=True)

    def _first(*keys: str) -> str:
        for key in keys:
            values = parsed.get(key)
            if values and values[0]:
                return values[0]
        return ""

    user = _first("user", "username").strip()
    pwd = _first("pass", "password", "pwd", "passwd")
    return user, pwd


def resolve_mediamtx_auth_fields(body: dict[str, Any]) -> tuple[str, str, str, str]:
    """Extract user, password, path, action from a MediaMTX authHTTP POST body."""
    user = str(body.get("user") or "").strip()
    pwd = str(body.get("password") or "")
    path = str(body.get("path") or "")
    action = str(body.get("action") or "")
    path_query = ""
    if "?" in path:
        path, _, path_query = path.partition("?")
    query = _merge_query_strings(str(body.get("query") or ""), path_query)

    if query:
        q_user, q_pwd = _credentials_from_query_string(query)
        if not user and q_user:
            user = q_user
        if not pwd and q_pwd:
            pwd = q_pwd

    return user, pwd, path.strip(), action


def mediamtx_auth_query_diag(body: dict[str, Any]) -> dict[str, bool | int]:
    """Safe authHTTP diagnostics — no credential values."""
    path = str(body.get("path") or "")
    query = _merge_query_strings(str(body.get("query") or ""), path.partition("?")[2] if "?" in path else "")
    parsed = parse_qs(query, keep_blank_values=True) if query else {}
    return {
        "path_has_query": "?" in path,
        "query_field_nonempty": bool(str(body.get("query") or "").strip()),
        "query_len": len(query),
        "query_has_user_key": any(k in parsed for k in ("user", "username")),
        "query_has_pass_key": any(k in parsed for k in ("pass", "password", "pwd", "passwd")),
    }
