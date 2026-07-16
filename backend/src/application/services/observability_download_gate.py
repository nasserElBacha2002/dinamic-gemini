"""Concurrency and temp-dir guards for Observability artifact downloads."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active = 0


@contextmanager
def acquire_download_slot(*, max_concurrent: int) -> Iterator[None]:
    """Bound concurrent Observability downloads; raise 503 when saturated."""
    global _active
    limit = max(1, int(max_concurrent or 1))
    with _lock:
        if _active >= limit:
            logger.warning(
                "observability_download_concurrency_rejected active=%s limit=%s",
                _active,
                limit,
            )
            raise HTTPException(
                status_code=503,
                detail="Download capacity exceeded; retry later",
            )
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active = max(0, _active - 1)


def content_disposition_attachment(filename: str) -> str:
    """RFC 5987 Content-Disposition for ASCII fallback + UTF-8 filename*."""
    from urllib.parse import quote

    cleaned = "".join(
        c for c in (filename or "download").replace("\r", "").replace("\n", "") if c not in {'"', "\\", "/"}
    ).strip() or "download"
    # ASCII fallback: strip non-ascii
    ascii_name = cleaned.encode("ascii", errors="ignore").decode("ascii").strip() or "download"
    utf8_name = quote(cleaned, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
