"""SQL Server compare-and-set operational promotion — Phase 2 Part 3."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.ports.operational_job_promotion import (
    OperationalJobPromotionRepository,
    PromotionOutcome,
    PromotionResult,
)
from src.database.sqlserver import SqlServerClient

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlOperationalJobPromotionRepository(OperationalJobPromotionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def promote_if_eligible(
        self,
        *,
        aisle_id: str,
        candidate_job_id: str,
        candidate_created_at: object,
    ) -> PromotionResult:
        if not isinstance(candidate_created_at, datetime):
            return PromotionResult(
                outcome=PromotionOutcome.CONFLICT,
                previous_job_id=None,
                operational_job_id=None,
            )
        created = _ensure_utc(candidate_created_at)

        with self._client.cursor() as cur:
            cur.execute(
                "SELECT operational_job_id FROM aisles WHERE id = ?",
                (aisle_id,),
            )
            row = cur.fetchone()
            if row is None:
                return PromotionResult(
                    outcome=PromotionOutcome.REJECTED_AISLE_NOT_FOUND,
                    previous_job_id=None,
                    operational_job_id=None,
                )
            previous = getattr(row, "operational_job_id", None)
            if previous == candidate_job_id:
                return PromotionResult(
                    outcome=PromotionOutcome.ALREADY_OPERATIONAL,
                    previous_job_id=previous,
                    operational_job_id=previous,
                )

            cur.execute(
                """
                UPDATE a
                SET operational_job_id = ?
                FROM aisles a
                WHERE a.id = ?
                  AND (
                      a.operational_job_id IS NULL
                      OR a.operational_job_id = ?
                      OR NOT EXISTS (
                          SELECT 1
                          FROM inventory_jobs cur
                          WHERE cur.id = a.operational_job_id
                            AND cur.created_at > ?
                      )
                  )
                """,
                (candidate_job_id, aisle_id, candidate_job_id, created),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "SELECT operational_job_id FROM aisles WHERE id = ?",
                    (aisle_id,),
                )
                after = cur.fetchone()
                current = getattr(after, "operational_job_id", None) if after else previous
                return PromotionResult(
                    outcome=PromotionOutcome.REJECTED_STALE,
                    previous_job_id=previous,
                    operational_job_id=current,
                )

        return PromotionResult(
            outcome=PromotionOutcome.PROMOTED,
            previous_job_id=previous,
            operational_job_id=candidate_job_id,
        )
