"""
SQL Server implementation of ProductRecordRepository — v3.0 Épica 6.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.ports.repositories import ProductRecordRepository
from src.database.sqlserver import SqlServerClient
from src.domain.products.entities import ProductRecord


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_product(row) -> ProductRecord:
    pid = getattr(row, "id", "")
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("product_records row missing required created_at/updated_at")
    return ProductRecord(
        id=pid,
        position_id=row.position_id or "",
        sku=row.sku or "",
        description=getattr(row, "description", None),
        detected_quantity=int(getattr(row, "detected_quantity", 0)),
        corrected_quantity=int(row.corrected_quantity) if getattr(row, "corrected_quantity", None) is not None else None,
        confidence=float(getattr(row, "confidence", 0)),
        created_at=created,
        updated_at=updated,
    )


class SqlProductRecordRepository(ProductRecordRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, product: ProductRecord) -> None:
        if product.created_at is None or product.updated_at is None:
            raise ValueError("ProductRecord created_at and updated_at are required")
        created = _ensure_utc(product.created_at)
        updated = _ensure_utc(product.updated_at)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE product_records
                SET position_id = ?, sku = ?, description = ?, detected_quantity = ?, corrected_quantity = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    product.position_id,
                    product.sku,
                    product.description,
                    product.detected_quantity,
                    product.corrected_quantity,
                    product.confidence,
                    updated,
                    product.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO product_records (id, position_id, sku, description, detected_quantity, corrected_quantity, confidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product.id,
                        product.position_id,
                        product.sku,
                        product.description,
                        product.detected_quantity,
                        product.corrected_quantity,
                        product.confidence,
                        created,
                        updated,
                    ),
                )

    def get_by_id(self, product_id: str) -> Optional[ProductRecord]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, position_id, sku, description, detected_quantity, corrected_quantity, confidence, created_at, updated_at
                FROM product_records WHERE id = ?
                """,
                (product_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_product(row)

    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, position_id, sku, description, detected_quantity, corrected_quantity, confidence, created_at, updated_at
                FROM product_records WHERE position_id = ? ORDER BY created_at ASC, id ASC
                """,
                (position_id,),
            )
            rows = cur.fetchall()
        return [_row_to_product(row) for row in rows]
