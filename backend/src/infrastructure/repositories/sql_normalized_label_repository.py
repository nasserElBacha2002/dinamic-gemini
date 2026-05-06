"""
SQL Server implementation of NormalizedLabelRepository — v3.2.3.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import LabelJobScope, NormalizedLabelRepository
from src.database.sqlserver import SqlServerClient
from src.domain.labels.entities import NormalizedLabel


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _safe_dump_json(v: object) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(v), ensure_ascii=False)


def _safe_load_json(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str) and raw.strip():
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {"value": v}
        except json.JSONDecodeError:
            return {"value": raw}
    if isinstance(raw, dict):
        return raw
    return {"value": raw}


def _safe_load_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip():
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [str(x) for x in v]
        except json.JSONDecodeError:
            return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def _sql_job_predicate(job_id: LabelJobScope) -> tuple[str, list]:
    if job_id == "all":
        return "", []
    if job_id is None:
        return " AND job_id IS NULL", []
    return " AND job_id = ?", [job_id]


def _row_to_normalized_label(row) -> NormalizedLabel:
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("normalized_labels row missing required created_at")
    return NormalizedLabel(
        id=getattr(row, "id", "") or "",
        inventory_id=getattr(row, "inventory_id", "") or "",
        aisle_id=getattr(row, "aisle_id", "") or "",
        position_id=getattr(row, "position_id", None),
        group_key=getattr(row, "group_key", "") or "",
        canonical_sku=getattr(row, "canonical_sku", None),
        canonical_product_name=getattr(row, "canonical_product_name", None),
        raw_label_ids=_safe_load_list(getattr(row, "raw_label_ids_json", None)),
        merge_rule_applied=getattr(row, "merge_rule_applied", "") or "",
        merge_confidence=float(getattr(row, "merge_confidence", 0))
        if getattr(row, "merge_confidence", None) is not None
        else None,
        merge_reason=getattr(row, "merge_reason", "") or "",
        review_required=bool(getattr(row, "review_required", False)),
        metadata=_safe_load_json(getattr(row, "metadata_json", None)),
        created_at=created,
        job_id=getattr(row, "job_id", None),
    )


class SqlNormalizedLabelRepository(NormalizedLabelRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save_many(self, labels: list[NormalizedLabel]) -> None:
        if not labels:
            return
        with self._client.cursor() as cur:
            for lb in labels:
                created = _ensure_utc(lb.created_at)
                if created is None:
                    raise ValueError("NormalizedLabel.created_at is required")
                cur.execute(
                    """
                    MERGE normalized_labels AS target
                    USING (SELECT ? AS id) AS src
                    ON (target.id = src.id)
                    WHEN MATCHED THEN
                        UPDATE SET
                            inventory_id = ?,
                            aisle_id = ?,
                            position_id = ?,
                            group_key = ?,
                            canonical_sku = ?,
                            canonical_product_name = ?,
                            raw_label_ids_json = ?,
                            merge_rule_applied = ?,
                            merge_confidence = ?,
                            merge_reason = ?,
                            review_required = ?,
                            metadata_json = ?,
                            created_at = ?,
                            job_id = ?
                    WHEN NOT MATCHED THEN
                        INSERT (
                            id, inventory_id, aisle_id, position_id, group_key,
                            canonical_sku, canonical_product_name, raw_label_ids_json,
                            merge_rule_applied, merge_confidence, merge_reason, review_required,
                            metadata_json, created_at, job_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        lb.id,
                        lb.inventory_id,
                        lb.aisle_id,
                        lb.position_id,
                        lb.group_key,
                        lb.canonical_sku,
                        lb.canonical_product_name,
                        _safe_dump_json(lb.raw_label_ids),
                        lb.merge_rule_applied,
                        lb.merge_confidence,
                        lb.merge_reason,
                        lb.review_required,
                        _safe_dump_json(lb.metadata or {}),
                        created,
                        lb.job_id,
                        lb.id,
                        lb.inventory_id,
                        lb.aisle_id,
                        lb.position_id,
                        lb.group_key,
                        lb.canonical_sku,
                        lb.canonical_product_name,
                        _safe_dump_json(lb.raw_label_ids),
                        lb.merge_rule_applied,
                        lb.merge_confidence,
                        lb.merge_reason,
                        lb.review_required,
                        _safe_dump_json(lb.metadata or {}),
                        created,
                        lb.job_id,
                    ),
                )

    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[NormalizedLabel]:
        extra_sql, extra_params = _sql_job_predicate(job_id)
        # extra_sql from _sql_job_predicate only (see module helper).
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, inventory_id, aisle_id, position_id, group_key, canonical_sku, canonical_product_name,
                    raw_label_ids_json, merge_rule_applied, merge_confidence, merge_reason, review_required,
                    metadata_json, created_at, job_id
                FROM normalized_labels
                WHERE inventory_id = ? AND aisle_id = ?{extra_sql}
                ORDER BY created_at ASC, id ASC
                """,  # nosec B608
                (inventory_id, aisle_id, *extra_params),
            )
            rows = cur.fetchall()
        return [_row_to_normalized_label(r) for r in rows]

    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        extra_sql, extra_params = _sql_job_predicate(job_id)
        with self._client.cursor() as cur:
            cur.execute(
                f"DELETE FROM normalized_labels WHERE inventory_id = ? AND aisle_id = ?{extra_sql}",  # nosec B608
                (inventory_id, aisle_id, *extra_params),
            )
