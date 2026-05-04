"""
SQL Server implementation of ProductRecordRepository — v3.0 Épica 6.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import ProductRecordRepository
from src.database.sqlserver import SqlServerClient
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _description_from_row(raw: object) -> str | None:
    return optional_nonempty_db_str(raw)


def _ensure_utc(dt: datetime | None) -> datetime | None:
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
        position_id=normalize_db_str(getattr(row, "position_id", None)),
        sku=normalize_db_str(getattr(row, "sku", None)),
        description=_description_from_row(getattr(row, "description", None)),
        detected_quantity=int(getattr(row, "detected_quantity", 0)),
        corrected_quantity=int(row.corrected_quantity)
        if getattr(row, "corrected_quantity", None) is not None
        else None,
        confidence=float(getattr(row, "confidence", 0)),
        created_at=created,
        updated_at=updated,
        qty_source=getattr(row, "qty_source", None),
        qty_inference_reason=getattr(row, "qty_inference_reason", None),
        raw_qty=_safe_load_json(getattr(row, "raw_qty_json", None)),
        qty_parse_status=getattr(row, "qty_parse_status", None),
    )


def _safe_dump_json(v: object) -> str | None:
    if v is None:
        return None
    try:
        return json.dumps(v, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(v), ensure_ascii=False)


def _safe_load_json(raw: object) -> object | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            parsed: object = json.loads(raw)
            return parsed
        except json.JSONDecodeError:
            out_raw: object = raw
            return out_raw
    out_other: object = raw
    return out_other


class SqlProductRecordRepository(ProductRecordRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, product: ProductRecord) -> None:
        if product.created_at is None or product.updated_at is None:
            raise ValueError("ProductRecord created_at and updated_at are required")
        created = _ensure_utc(product.created_at)
        updated = _ensure_utc(product.updated_at)
        raw_qty_json = _safe_dump_json(product.raw_qty)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE product_records
                SET position_id = ?, sku = ?, description = ?, detected_quantity = ?, corrected_quantity = ?, confidence = ?,
                    updated_at = ?, qty_source = ?, qty_inference_reason = ?, raw_qty_json = ?, qty_parse_status = ?
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
                    (product.qty_source or None),
                    (product.qty_inference_reason or None),
                    raw_qty_json,
                    (product.qty_parse_status or None),
                    product.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO product_records (
                        id, position_id, sku, description, detected_quantity, corrected_quantity, confidence,
                        created_at, updated_at, qty_source, qty_inference_reason, raw_qty_json, qty_parse_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        (product.qty_source or None),
                        (product.qty_inference_reason or None),
                        raw_qty_json,
                        (product.qty_parse_status or None),
                    ),
                )

    def get_by_id(self, product_id: str) -> ProductRecord | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, position_id, sku, description, detected_quantity, corrected_quantity, confidence,
                       created_at, updated_at, qty_source, qty_inference_reason, raw_qty_json, qty_parse_status
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
                SELECT id, position_id, sku, description, detected_quantity, corrected_quantity, confidence,
                       created_at, updated_at, qty_source, qty_inference_reason, raw_qty_json, qty_parse_status
                FROM product_records WHERE position_id = ? ORDER BY created_at ASC, id ASC
                """,
                (position_id,),
            )
            rows = cur.fetchall()
        return [_row_to_product(row) for row in rows]

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        if not position_ids:
            return []
        uniq: list[str] = list(dict.fromkeys(position_ids))
        if not uniq:
            return []
        placeholders = ",".join("?" * len(uniq))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, position_id, sku, description, detected_quantity, corrected_quantity, confidence,
                       created_at, updated_at, qty_source, qty_inference_reason, raw_qty_json, qty_parse_status
                FROM product_records
                WHERE position_id IN ({placeholders})
                ORDER BY position_id, created_at ASC, id ASC
                """,
                tuple(uniq),
            )
            rows = cur.fetchall()
        return [_row_to_product(row) for row in rows]
