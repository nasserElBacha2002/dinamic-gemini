"""SQL Server claims for inventory-scoped product label_id uniqueness."""

from __future__ import annotations

from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
    InventoryCountedProductLabelRepository,
)
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import sql_repository_cursor


class SqlInventoryCountedProductLabelRepository(InventoryCountedProductLabelRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def try_claim(self, row: InventoryCountedProductLabel) -> bool:
        try:
            with sql_repository_cursor(self._client, connection=self._connection) as cur:
                cur.execute(
                    """
                    INSERT INTO inventory_counted_product_labels (
                        id, inventory_id, label_id, first_product_record_id,
                        first_source_asset_id, first_job_id, first_position_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.id,
                        row.inventory_id,
                        row.label_id.upper(),
                        row.first_product_record_id,
                        row.first_source_asset_id,
                        row.first_job_id,
                        row.first_position_id,
                        row.created_at,
                    ),
                )
            return True
        except Exception as exc:
            # Unique violation → already counted in this inventory.
            msg = str(exc).lower()
            if "unique" in msg or "2627" in msg or "2601" in msg or "duplicate" in msg:
                return False
            raise

    def get(self, inventory_id: str, label_id: str) -> InventoryCountedProductLabel | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, label_id, first_product_record_id,
                       first_source_asset_id, first_job_id, first_position_id, created_at
                FROM inventory_counted_product_labels
                WHERE inventory_id = ? AND label_id = ?
                """,
                (inventory_id, label_id.upper()),
            )
            row = cur.fetchone()
        if not row:
            return None
        return InventoryCountedProductLabel(
            id=str(row.id),
            inventory_id=str(row.inventory_id),
            label_id=str(row.label_id),
            first_product_record_id=str(row.first_product_record_id),
            first_source_asset_id=str(row.first_source_asset_id),
            first_job_id=str(row.first_job_id),
            first_position_id=str(row.first_position_id),
            created_at=row.created_at,
        )
