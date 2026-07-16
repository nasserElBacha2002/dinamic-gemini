"""SQL Server JobImageCoverageRepository — paginated snapshot + aggregate counters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.application.ports.job_image_coverage_repository import (
    JobImageCoverageCounters,
    JobImageCoverageSnapshotRow,
    ResultStatusFilter,
)
from src.application.services.job_image_result_resolution import index_positions_by_source_asset
from src.database.sqlserver import SqlServerClient
from src.domain.positions.entities import Position
from src.infrastructure.database.sql_transaction import sql_repository_cursor
from src.infrastructure.repositories.sql_position_repository import _row_to_position
from src.infrastructure.repositories.sql_result_evidence_repository import (
    SqlResultEvidenceRepository,
)

# Canonical primary photo rows for a job (one per source_asset_id, min position_order).
_CANONICAL_PHOTOS_CTE = """
;WITH ranked AS (
    SELECT
        jsa.id AS job_source_asset_id,
        LTRIM(RTRIM(jsa.source_asset_id)) AS source_asset_id,
        jsa.job_id,
        jsa.original_filename,
        jsa.created_at,
        jsa.position_order,
        jsa.mime_type,
        jsa.storage_key,
        ROW_NUMBER() OVER (
            PARTITION BY LTRIM(RTRIM(jsa.source_asset_id))
            ORDER BY jsa.position_order ASC, jsa.id ASC
        ) AS rn
    FROM job_source_assets jsa
    WHERE jsa.job_id = ?
      AND LOWER(LTRIM(RTRIM(ISNULL(jsa.asset_role, N'')))) = N'primary'
      AND LTRIM(RTRIM(ISNULL(jsa.source_asset_id, N''))) <> N''
),
canonical AS (
    SELECT
        job_source_asset_id,
        source_asset_id,
        job_id,
        original_filename,
        created_at,
        position_order,
        mime_type,
        storage_key
    FROM ranked
    WHERE rn = 1
)
"""

# Image has a linked position for this job/aisle via evidence keys or detected_summary JSON.
_HAS_RESULT_EXISTS = """
EXISTS (
    SELECT 1
    FROM result_evidence re
    INNER JOIN positions p ON p.id = re.position_id
    WHERE re.job_id = ?
      AND p.job_id = ?
      AND p.aisle_id = ?
      AND (
          LTRIM(RTRIM(ISNULL(re.source_asset_id, N''))) = c.source_asset_id
          OR LTRIM(RTRIM(ISNULL(re.source_image_id, N''))) = c.source_asset_id
      )
)
OR EXISTS (
    SELECT 1
    FROM positions p
    WHERE p.job_id = ?
      AND p.aisle_id = ?
      AND (
          LTRIM(RTRIM(ISNULL(JSON_VALUE(p.detected_summary_json, N'$.source_asset_id'), N'')))
              = c.source_asset_id
          OR LTRIM(RTRIM(ISNULL(JSON_VALUE(p.detected_summary_json, N'$.source_image_id'), N'')))
              = c.source_asset_id
      )
)
"""


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_snapshot(row: Any) -> JobImageCoverageSnapshotRow:
    created = getattr(row, "created_at", None)
    if not isinstance(created, datetime):
        created = datetime.now(timezone.utc)
    else:
        created = _ensure_utc(created)
    return JobImageCoverageSnapshotRow(
        job_source_asset_id=str(getattr(row, "job_source_asset_id", "") or ""),
        source_asset_id=str(getattr(row, "source_asset_id", "") or ""),
        job_id=str(getattr(row, "job_id", "") or ""),
        original_filename=(
            str(getattr(row, "original_filename", None))
            if getattr(row, "original_filename", None) is not None
            else None
        ),
        created_at=created,
        position_order=int(getattr(row, "position_order", 0) or 0),
        mime_type=(
            str(getattr(row, "mime_type", None))
            if getattr(row, "mime_type", None) is not None
            else None
        ),
        storage_key=(
            str(getattr(row, "storage_key", None))
            if getattr(row, "storage_key", None) is not None
            else None
        ),
    )


def _result_link_params(job_id: str, aisle_id: str) -> tuple[str, ...]:
    """Params for ``_HAS_RESULT_EXISTS`` (evidence branch ×3 + JSON branch ×2)."""
    return (job_id, job_id, aisle_id, job_id, aisle_id)


def _status_filter_sql(result_status: ResultStatusFilter) -> str:
    status = (result_status or "all").strip().lower()
    if status == "with_result":
        return f"AND ({_HAS_RESULT_EXISTS})"
    if status == "without_result":
        return f"AND NOT ({_HAS_RESULT_EXISTS})"
    return ""


class SqlJobImageCoverageRepository:
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def get_counters(self, *, job_id: str, aisle_id: str) -> JobImageCoverageCounters:
        link_params = _result_link_params(job_id, aisle_id)
        # SQL Server forbids aggregates over expressions that contain subqueries
        # (e.g. SUM(CASE WHEN EXISTS(...))). Compute has_result in a CTE first.
        sql = f"""
{_CANONICAL_PHOTOS_CTE}
, flagged AS (
    SELECT
        CASE WHEN ({_HAS_RESULT_EXISTS}) THEN 1 ELSE 0 END AS has_result
    FROM canonical c
)
SELECT
    COUNT(*) AS total_images,
    COALESCE(SUM(has_result), 0) AS with_result,
    COALESCE(SUM(CASE WHEN has_result = 0 THEN 1 ELSE 0 END), 0) AS without_result
FROM flagged
"""  # nosec B608 — static fragments only; values bound as ?
        params: list[Any] = [job_id, *link_params]
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        if not row:
            return JobImageCoverageCounters(total_images=0, with_result=0, without_result=0)
        total = int(getattr(row, "total_images", 0) or 0)
        with_result = int(getattr(row, "with_result", 0) or 0)
        without_result = int(getattr(row, "without_result", 0) or 0)
        return JobImageCoverageCounters(
            total_images=total,
            with_result=with_result,
            without_result=without_result,
        )

    def list_snapshot_page(
        self,
        *,
        job_id: str,
        aisle_id: str,
        result_status: ResultStatusFilter,
        page: int,
        page_size: int,
    ) -> tuple[tuple[JobImageCoverageSnapshotRow, ...], int]:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        offset = (page - 1) * page_size
        status: ResultStatusFilter
        raw_status = (result_status or "all").strip().lower()
        if raw_status == "with_result":
            status = "with_result"
        elif raw_status == "without_result":
            status = "without_result"
        else:
            status = "all"
        filter_sql = _status_filter_sql(status)
        link_params = _result_link_params(job_id, aisle_id)

        count_sql = f"""
{_CANONICAL_PHOTOS_CTE}
SELECT COUNT(*) AS total_filtered
FROM canonical c
WHERE 1 = 1
{filter_sql}
"""  # nosec B608
        page_sql = f"""
{_CANONICAL_PHOTOS_CTE}
SELECT
    c.job_source_asset_id,
    c.source_asset_id,
    c.job_id,
    c.original_filename,
    c.created_at,
    c.position_order,
    c.mime_type,
    c.storage_key
FROM canonical c
WHERE 1 = 1
{filter_sql}
ORDER BY c.position_order ASC, c.source_asset_id ASC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""  # nosec B608

        count_params: list[Any] = [job_id]
        page_params: list[Any] = [job_id]
        if status in ("with_result", "without_result"):
            count_params.extend(link_params)
            page_params.extend(link_params)
        page_params.extend([offset, page_size])

        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(count_sql, count_params)
            count_row = cur.fetchone()
            total = int(getattr(count_row, "total_filtered", 0) or 0) if count_row else 0
            cur.execute(page_sql, page_params)
            rows = cur.fetchall()
        return tuple(_row_to_snapshot(r) for r in rows), total

    def load_positions_for_assets(
        self,
        *,
        job_id: str,
        aisle_id: str,
        source_asset_ids: tuple[str, ...],
    ) -> dict[str, list[Position]]:
        coverage = frozenset(aid.strip() for aid in source_asset_ids if aid and aid.strip())
        if not coverage:
            return {}

        evidence_repo = SqlResultEvidenceRepository(self._client, connection=self._connection)
        evidence_rows = list(evidence_repo.list_by_job_id(job_id))

        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, aisle_id, status, review_resolution, confidence, needs_review,
                       primary_evidence_id, created_at, updated_at, detected_summary_json,
                       corrected_summary_json, corrected_position_code, job_id, creation_source
                FROM positions
                WHERE aisle_id = ? AND job_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (aisle_id, job_id),
            )
            position_rows = cur.fetchall()
        positions = [_row_to_position(r) for r in position_rows]
        return index_positions_by_source_asset(
            coverage_asset_ids=coverage,
            result_evidence=evidence_rows,
            positions=positions,
        )
