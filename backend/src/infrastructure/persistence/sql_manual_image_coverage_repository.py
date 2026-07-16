"""SQL Server ManualImageCoverageRepository."""

from __future__ import annotations

from typing import Any

from src.application.errors import ManualResultAlreadyExistsError
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _row_to_link(row: Any) -> ManualImageCoverageLink:
    return ManualImageCoverageLink(
        id=str(row.id),
        job_id=str(row.job_id),
        job_source_asset_id=str(getattr(row, "job_source_asset_id", "") or ""),
        source_asset_id=str(row.source_asset_id),
        position_id=str(row.position_id),
        aisle_id=str(row.aisle_id),
        inventory_id=str(row.inventory_id),
        created_by_user_id=getattr(row, "created_by_user_id", None),
        created_at=row.created_at,
    )


class SqlManualImageCoverageRepository:
    def __init__(self, client: Any, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def get_by_job_and_asset(
        self, job_id: str, source_asset_id: str
    ) -> ManualImageCoverageLink | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, job_id, job_source_asset_id, source_asset_id, position_id, aisle_id, inventory_id,
                       created_by_user_id, created_at
                FROM position_manual_image_coverage
                WHERE job_id = ? AND source_asset_id = ?
                """,
                (job_id, source_asset_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_link(row)

    def save(self, link: ManualImageCoverageLink) -> None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO position_manual_image_coverage (
                        id, job_id, job_source_asset_id, source_asset_id, position_id, aisle_id, inventory_id,
                        created_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        link.id,
                        link.job_id,
                        link.job_source_asset_id,
                        link.source_asset_id,
                        link.position_id,
                        link.aisle_id,
                        link.inventory_id,
                        link.created_by_user_id,
                        link.created_at,
                    ),
                )
            except Exception as exc:
                # pyodbc IntegrityError / unique violation → 409 domain error
                msg = str(exc).lower()
                if "uq_manual_coverage_job_asset" in msg or "unique" in msg or "2627" in msg or "2601" in msg:
                    raise ManualResultAlreadyExistsError(
                        "La imagen ya tiene un resultado manual asociado."
                    ) from exc
                raise

    def list_by_job(self, job_id: str) -> list[ManualImageCoverageLink]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, job_id, job_source_asset_id, source_asset_id, position_id, aisle_id, inventory_id,
                       created_by_user_id, created_at
                FROM position_manual_image_coverage
                WHERE job_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_link(r) for r in rows]
