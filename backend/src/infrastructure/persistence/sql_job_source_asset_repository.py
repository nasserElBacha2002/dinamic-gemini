"""SQL Server JobSourceAssetRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import sql_repository_cursor


class SqlJobSourceAssetRepository:
    def __init__(self, client: SqlServerClient, *, connection: Any | None = None) -> None:
        self._client = client
        self._connection = connection

    def replace_for_job(self, job_id: str, links: Sequence[JobSourceAssetLink]) -> None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute("DELETE FROM job_source_assets WHERE job_id = ?", (job_id,))
            for link in links:
                cur.execute(
                    """
                    INSERT INTO job_source_assets (
                        id, job_id, source_asset_id, asset_role, position_order,
                        checksum, storage_key, mime_type, size_bytes, width, height,
                        stage, provider_request_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        link.id,
                        link.job_id,
                        link.source_asset_id,
                        link.asset_role,
                        int(link.position_order),
                        link.checksum,
                        link.storage_key,
                        link.mime_type,
                        link.size_bytes,
                        link.width,
                        link.height,
                        link.stage,
                        link.provider_request_id,
                        link.created_at,
                    ),
                )

    def list_for_job(self, job_id: str) -> list[JobSourceAssetLink]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, job_id, source_asset_id, asset_role, position_order,
                       checksum, storage_key, mime_type, size_bytes, width, height,
                       stage, provider_request_id, created_at
                FROM job_source_assets
                WHERE job_id = ?
                ORDER BY position_order ASC, asset_role ASC, id ASC
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_link(r) for r in rows]


def _row_to_link(row: Any) -> JobSourceAssetLink:
    def _g(name: str, idx: int) -> Any:
        if hasattr(row, name):
            return getattr(row, name)
        return row[idx]

    created = _g("created_at", 13)
    if not isinstance(created, datetime):
        created = datetime.now(timezone.utc)
    elif created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return JobSourceAssetLink(
        id=str(_g("id", 0)),
        job_id=str(_g("job_id", 1)),
        source_asset_id=str(_g("source_asset_id", 2)),
        asset_role=str(_g("asset_role", 3)),
        position_order=int(_g("position_order", 4) or 0),
        checksum=(str(_g("checksum", 5)) if _g("checksum", 5) is not None else None),
        storage_key=(str(_g("storage_key", 6)) if _g("storage_key", 6) is not None else None),
        mime_type=(str(_g("mime_type", 7)) if _g("mime_type", 7) is not None else None),
        size_bytes=(int(_g("size_bytes", 8)) if _g("size_bytes", 8) is not None else None),
        width=(int(_g("width", 9)) if _g("width", 9) is not None else None),
        height=(int(_g("height", 10)) if _g("height", 10) is not None else None),
        stage=(str(_g("stage", 11)) if _g("stage", 11) is not None else None),
        provider_request_id=(
            str(_g("provider_request_id", 12))
            if _g("provider_request_id", 12) is not None
            else None
        ),
        created_at=created,
    )
