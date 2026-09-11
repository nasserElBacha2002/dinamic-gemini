"""Scoped SQL reader for durable detection-to-location associations."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.materialized_position_identity_reader import (
    TrustedMaterializedPositionIdentity,
)
from src.database.sqlserver import SqlServerClient
from src.infrastructure.repositories.db_row_text import normalize_db_str


class SqlMaterializedPositionIdentityReader:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def read_by_detection_ids(
        self,
        detection_ids: Sequence[str],
        *,
        client_id: str,
        inventory_id: str,
        aisle_id: str,
    ) -> dict[str, TrustedMaterializedPositionIdentity]:
        ids = tuple(dict.fromkeys(value for value in detection_ids if value))
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        sql = f"""
        SELECT r.source_detection_id, r.request_id, mr.location_id
        FROM dbo.position_materialization_association_receipts r
        INNER JOIN dbo.position_materialization_requests mr ON mr.id = r.request_id
        INNER JOIN dbo.aisle_locations loc ON loc.id = mr.location_id
        INNER JOIN dbo.aisles a ON a.id = loc.aisle_id
        WHERE r.source_detection_id IN ({placeholders})
          AND r.target_type = 'IMAGE_RESULT'
          AND mr.association_status = 'ASSOCIATED'
          AND mr.client_id = ? AND mr.inventory_id = ? AND mr.aisle_id = ?
          AND loc.client_id = ? AND loc.aisle_id = ? AND loc.status = 'ACTIVE'
          AND a.inventory_id = ?
        """  # nosec B608 -- placeholders are generated, values remain parameters.
        params = (*ids, client_id, inventory_id, aisle_id, client_id, aisle_id, inventory_id)
        with self._client.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return {
            normalize_db_str(row.source_detection_id): TrustedMaterializedPositionIdentity(
                detection_id=normalize_db_str(row.source_detection_id),
                request_id=normalize_db_str(row.request_id),
                aisle_location_id=normalize_db_str(row.location_id),
            )
            for row in rows
        }
