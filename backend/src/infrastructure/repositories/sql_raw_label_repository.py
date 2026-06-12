"""
SQL Server implementation of RawLabelRepository — v3.2.3.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import LabelJobScope, RawLabelRepository
from src.database.sqlserver import SqlServerClient
from src.domain.labels.entities import RawLabel
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _safe_dump_json(v: object) -> str | None:
    if v is None:
        return None
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


def _sql_job_predicate(job_id: LabelJobScope) -> tuple[str, list]:
    if job_id == "all":
        return "", []
    if job_id is None:
        return " AND job_id IS NULL", []
    return " AND job_id = ?", [job_id]


def _row_to_raw_label(row) -> RawLabel:
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("raw_labels row missing required created_at")
    return RawLabel(
        id=getattr(row, "id", "") or "",
        inventory_id=getattr(row, "inventory_id", "") or "",
        aisle_id=getattr(row, "aisle_id", "") or "",
        position_id=getattr(row, "position_id", None),
        evidence_id=getattr(row, "evidence_id", None),
        group_key=getattr(row, "group_key", "") or "",
        provider=getattr(row, "provider", "") or "",
        source_type=getattr(row, "source_type", "") or "",
        source_reference=getattr(row, "source_reference", None),
        sku_raw=getattr(row, "sku_raw", None),
        sku_candidate=getattr(row, "sku_candidate", None),
        product_name_raw=getattr(row, "product_name_raw", None),
        detected_text=getattr(row, "detected_text", None),
        confidence=float(getattr(row, "confidence", 0))
        if getattr(row, "confidence", None) is not None
        else None,
        metadata=_safe_load_json(getattr(row, "metadata_json", None)),
        created_at=created,
        job_id=getattr(row, "job_id", None),
    )


class SqlRawLabelRepository(RawLabelRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def save_many(self, labels: list[RawLabel]) -> None:
        if not labels:
            return
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            for lb in labels:
                created = _ensure_utc(lb.created_at)
                if created is None:
                    raise ValueError("RawLabel.created_at is required")
                cur.execute(
                    """
                    MERGE raw_labels AS target
                    USING (SELECT ? AS id) AS src
                    ON (target.id = src.id)
                    WHEN MATCHED THEN
                        UPDATE SET
                            inventory_id = ?,
                            aisle_id = ?,
                            position_id = ?,
                            evidence_id = ?,
                            group_key = ?,
                            provider = ?,
                            source_type = ?,
                            source_reference = ?,
                            sku_raw = ?,
                            sku_candidate = ?,
                            product_name_raw = ?,
                            detected_text = ?,
                            confidence = ?,
                            metadata_json = ?,
                            created_at = ?,
                            job_id = ?
                    WHEN NOT MATCHED THEN
                        INSERT (
                            id, inventory_id, aisle_id, position_id, evidence_id, group_key,
                            provider, source_type, source_reference,
                            sku_raw, sku_candidate, product_name_raw, detected_text, confidence,
                            metadata_json, created_at, job_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        lb.id,
                        lb.inventory_id,
                        lb.aisle_id,
                        lb.position_id,
                        lb.evidence_id,
                        lb.group_key,
                        lb.provider,
                        lb.source_type,
                        lb.source_reference,
                        lb.sku_raw,
                        lb.sku_candidate,
                        lb.product_name_raw,
                        lb.detected_text,
                        lb.confidence,
                        _safe_dump_json(lb.metadata),
                        created,
                        lb.job_id,
                        lb.id,
                        lb.inventory_id,
                        lb.aisle_id,
                        lb.position_id,
                        lb.evidence_id,
                        lb.group_key,
                        lb.provider,
                        lb.source_type,
                        lb.source_reference,
                        lb.sku_raw,
                        lb.sku_candidate,
                        lb.product_name_raw,
                        lb.detected_text,
                        lb.confidence,
                        _safe_dump_json(lb.metadata),
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
    ) -> Sequence[RawLabel]:
        extra_sql, extra_params = _sql_job_predicate(job_id)
        # extra_sql from _sql_job_predicate only (see module helper).
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT
                    id, inventory_id, aisle_id, position_id, evidence_id, group_key, provider, source_type,
                    source_reference, sku_raw, sku_candidate, product_name_raw, detected_text, confidence,
                    metadata_json, created_at, job_id
                FROM raw_labels
                WHERE inventory_id = ? AND aisle_id = ?{extra_sql}
                ORDER BY created_at ASC, id ASC
                """,  # nosec B608
                (inventory_id, aisle_id, *extra_params),
            )
            rows = cur.fetchall()
        return [_row_to_raw_label(r) for r in rows]
