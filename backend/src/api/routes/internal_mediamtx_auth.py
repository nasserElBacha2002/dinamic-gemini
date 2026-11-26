"""MediaMTX authHTTP callback — no JWT.

MediaMTX 1.11.x cannot attach custom HTTP headers to authHTTP requests.
Service-to-service authentication uses a query parameter on authHTTPAddress
(see render_mediamtx_config_phase3.py). Optional header supported for reverse-proxy setups.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.deps.live_stream import get_mediamtx_auth_service
from src.application.services.mediamtx_auth_credentials import (
    mediamtx_auth_query_diag,
    resolve_mediamtx_auth_fields,
)
from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/mediamtx", tags=["internal-mediamtx"])


def _validate_mtx_callback_secret(
    *,
    header_secret: str | None,
    query_secret: str | None,
) -> bool:
    expected = (load_settings().mediamtx_http_auth_secret or "").strip()
    if not expected:
        return False
    provided = (header_secret or query_secret or "").strip()
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


@router.post("/auth")
async def mediamtx_auth(
    request: Request,
    mtx_key: str | None = Query(default=None, alias="mtx_key"),
    x_mediamtx_auth_secret: str | None = Header(default=None, alias="X-MediaMTX-Auth-Secret"),
    auth_service: MediaMtxAuthService = Depends(get_mediamtx_auth_service),
) -> Response:
    if not _validate_mtx_callback_secret(
        header_secret=x_mediamtx_auth_secret,
        query_secret=mtx_key,
    ):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    user, pwd, path, action = resolve_mediamtx_auth_fields(body)
    decision = auth_service.authorize(
        username=user,
        password=pwd,
        path=path,
        action=action,
    )
    if not decision.allowed:
        diag = mediamtx_auth_query_diag(body)
        logger.info(
            "event=mediamtx_auth_http_denied user=%s path=%s action=%s has_password=%s "
            "path_has_query=%s query_field_nonempty=%s query_len=%s query_has_user_key=%s "
            "query_has_pass_key=%s",
            user or "(empty)",
            path,
            action,
            bool(pwd),
            diag["path_has_query"],
            diag["query_field_nonempty"],
            diag["query_len"],
            diag["query_has_user_key"],
            diag["query_has_pass_key"],
        )
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    payload: dict[str, str] = {}
    if decision.expire_at is not None:
        expire = decision.expire_at
        if expire.tzinfo is None:
            expire = expire.replace(tzinfo=timezone.utc)
        payload["expireAt"] = expire.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if payload:
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
    return Response(status_code=status.HTTP_200_OK)
