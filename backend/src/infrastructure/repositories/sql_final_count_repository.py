"""
SQL Server implementation of FinalCountRepository — v3.2.3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.ports.repositories import FinalCountRepository
from src.database.sqlserver import SqlServerClient
from src.domain.labels.entities import FinalCountRecord


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_final_count(row) -> FinalCountRecord:
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("final_count_records row missing required created_at")
    norm_ids_raw = getattr(row, "normalized_label_ids_json", None)
    try:
        norm_ids = json.loads(norm_ids_raw) if norm_ids_raw else []
    except json.JSONDecodeError:
        norm_ids = []
    metadata_raw = getattr(row, "metadata_json", None)
    try:
        metadata = json.loads(metadata_raw) if metadata_raw else {}
    except json.JSONDecodeError:
        metadata = {}
    return FinalCountRecord(
        id=getattr(row, "id", ""),
        inventory_id=getattr(row, "inventory_id", "") or "",
        aisle_id=getattr(row, "aisle_id", "") or "",
        position_id=getattr(row, "position_id", None),
        sku=getattr(row, "sku", None),
        product_name=getattr(row, "product_name", None),
        quantity=int(getattr(row, "quantity", 0)),
        normalized_label_ids=list(norm_ids),
        review_required=bool(getattr(row, "review_required", False)),
        explanation_summary=getattr(row, "explanation_summary", None),
        metadata=metadata,
        created_at=created,
    )


class SqlFinalCountRepository(FinalCountRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save_many(self, records: Sequence[FinalCountRecord]) -> None:
        if not records:
            return
        with self._client.cursor() as cur:
            for rec in records:
                created = _ensure_utc(rec.created_at)
                if created is None:
                    raise ValueError("FinalCountRecord.created_at is required")
                norm_ids_json = json.dumps(rec.normalized_label_ids, ensure_ascii=False)
                metadata_json = json.dumps(rec.metadata or {}, ensure_ascii=False)
                cur.execute(
                    """
                    MERGE final_count_records AS target
                    USING (SELECT ? AS id) AS src
                    ON (target.id = src.id)
                    WHEN MATCHED THEN
                        UPDATE SET
                            inventory_id = ?,
                            aisle_id = ?,
                            position_id = ?,
                            sku = ?,
                            product_name = ?,
                            quantity = ?,
                            normalized_label_ids_json = ?,
                            review_required = ?,
                            explanation_summary = ?,
                            metadata_json = ?,
                            created_at = ?
                    WHEN NOT MATCHED THEN
                        INSERT (
                            id,
                            inventory_id,
                            aisle_id,
                            position_id,
                            sku,
                            product_name,
                            quantity,
                            normalized_label_ids_json,
                            review_required,
                            explanation_summary,
                            metadata_json,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        rec.id,
                        rec.inventory_id,
                        rec.aisle_id,
                        rec.position_id,
                        rec.sku,
                        rec.product_name,
                        rec.quantity,
                        norm_ids_json,
                        rec.review_required,
                        rec.explanation_summary,
                        metadata_json,
                        created,
                        rec.id,
                        rec.inventory_id,
                        rec.aisle_id,
                        rec.position_id,
                        rec.sku,
                        rec.product_name,
                        rec.quantity,
                        norm_ids_json,
                        rec.review_required,
                        rec.explanation_summary,
                        metadata_json,
                        created,
                    ),
                )

    def list_for_scope(self, inventory_id: str, aisle_id: str) -> Sequence[FinalCountRecord]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    inventory_id,
                    aisle_id,
                    position_id,
                    sku,
                    product_name,
                    quantity,
                    normalized_label_ids_json,
                    review_required,
                    explanation_summary,
                    metadata_json,
                    created_at
                FROM final_count_records
                WHERE inventory_id = ? AND aisle_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (inventory_id, aisle_id),
            )
            rows = cur.fetchall()
        return [_row_to_final_count(row) for row in rows]

    def list_by_position(self, position_id: str) -> Sequence[FinalCountRecord]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    inventory_id,
                    aisle_id,
                    position_id,
                    sku,
                    product_name,
                    quantity,
                    normalized_label_ids_json,
                    review_required,
                    explanation_summary,
                    metadata_json,
                    created_at
                FROM final_count_records
                WHERE position_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (position_id,),
            )
            rows = cur.fetchall()
        return [_row_to_final_count(row) for row in rows]

    def replace_for_scope(self, inventory_id: str, aisle_id: str) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                "DELETE FROM final_count_records WHERE inventory_id = ? AND aisle_id = ?",
                (inventory_id, aisle_id),
            )

