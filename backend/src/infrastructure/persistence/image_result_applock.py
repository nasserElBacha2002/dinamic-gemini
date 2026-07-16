"""Shared application lock for coordinating manual vs automatic image results."""

from __future__ import annotations

import logging
from typing import Any

from src.application.errors import ImageResultLockTimeoutError

logger = logging.getLogger(__name__)

# Keep locks short: only cover EXISTS + writes (not payload validation).
DEFAULT_IMAGE_RESULT_LOCK_TIMEOUT_MS = 5_000


def image_result_lock_resource(*, job_id: str, source_asset_id: str) -> str:
    """Canonical lock key shared by manual create and pipeline persist."""
    return f"image-result:{(job_id or '').strip()}:{(source_asset_id or '').strip()}"


def acquire_image_result_applock(
    connection: Any,
    *,
    job_id: str,
    source_asset_id: str,
    timeout_ms: int = DEFAULT_IMAGE_RESULT_LOCK_TIMEOUT_MS,
) -> None:
    """
    Acquire an exclusive transaction-scoped applock for one job image.

    Must be called on an open transaction connection (``autocommit=False``).
    The lock is released automatically on COMMIT / ROLLBACK.
    """
    resource = image_result_lock_resource(job_id=job_id, source_asset_id=source_asset_id)
    if not resource.endswith(":") and resource.count(":") >= 2:
        pass
    jid = (job_id or "").strip()
    aid = (source_asset_id or "").strip()
    if not jid or not aid:
        raise ValueError("job_id and source_asset_id are required for image result lock")

    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            DECLARE @lock_result INT;
            EXEC @lock_result = sp_getapplock
                @Resource = ?,
                @LockMode = N'Exclusive',
                @LockOwner = N'Transaction',
                @LockTimeout = ?;
            SELECT @lock_result AS lock_result;
            """,
            (resource, int(timeout_ms)),
        )
        row = cursor.fetchone()
        code = int(getattr(row, "lock_result", row[0] if row else -999))
        if code < 0:
            logger.warning(
                "image_result_applock_failed resource=%s code=%s timeout_ms=%s",
                resource,
                code,
                timeout_ms,
            )
            raise ImageResultLockTimeoutError(
                "No se pudo adquirir el bloqueo de la imagen; reintentá en unos segundos."
            )
        logger.debug("image_result_applock_acquired resource=%s code=%s", resource, code)
    finally:
        cursor.close()
