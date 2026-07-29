"""SQL source for OperationalMetricsCollector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class SqlOperationalMetricsSource:
    def __init__(self, client: Any) -> None:
        self._client = client

    def count_jobs_by_status(self) -> dict[str, int]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) AS cnt FROM inventory_jobs GROUP BY status"
            )
            rows = cur.fetchall()
        out: dict[str, int] = {}
        for row in rows:
            status = getattr(row, "status", None)
            if status is None and isinstance(row, (tuple, list)):
                status = row[0]
            cnt = getattr(row, "cnt", None)
            if cnt is None and isinstance(row, (tuple, list)):
                cnt = row[1]
            out[str(status)] = int(cnt or 0)
        return out

    def count_active_leases(self) -> int:
        now = datetime.now(timezone.utc)
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM inventory_jobs
                WHERE status IN ('running', 'starting', 'cancel_requested')
                  AND claim_owner_id IS NOT NULL
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at >= ?
                """,
                (now,),
            )
            row = cur.fetchone()
        return int(getattr(row, "cnt", row[0] if row else 0) or 0)

    def count_expired_running_leases(self) -> int:
        now = datetime.now(timezone.utc)
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM inventory_jobs
                WHERE status IN ('running', 'starting', 'cancel_requested')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ?
                """,
                (now,),
            )
            row = cur.fetchone()
        return int(getattr(row, "cnt", row[0] if row else 0) or 0)

    def count_artifact_outbox(self) -> tuple[int, int]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN status IN ('pending', 'claimed', 'retry_scheduled') THEN 1 ELSE 0 END) AS pending_cnt,
                  SUM(CASE WHEN status = 'permanently_failed' THEN 1 ELSE 0 END) AS failed_cnt
                FROM artifact_publication_outbox
                """,
            )
            row = cur.fetchone()
        if row is None:
            return 0, 0
        pending = getattr(row, "pending_cnt", None)
        failed = getattr(row, "failed_cnt", None)
        if pending is None and isinstance(row, (tuple, list)):
            pending, failed = row[0], row[1]
        return int(pending or 0), int(failed or 0)
