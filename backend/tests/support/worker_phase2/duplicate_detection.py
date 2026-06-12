"""Duplicate vs repetition detection for Phase 2 idempotency characterization."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from src.domain.labels.entities import FinalCountRecord, NormalizedLabel, RawLabel
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord


def _duplicate_keys(keys: Iterable[Any]) -> dict[Any, int]:
    counts = Counter(keys)
    return {k: n for k, n in counts.items() if n > 1}


def entity_uid_from_position(position: Position) -> str | None:
    summary = position.detected_summary_json or {}
    uid = summary.get("entity_uid")
    return str(uid).strip() if uid is not None and str(uid).strip() else None


# --- Structural keys (persistence identity / expected uniqueness) ----------------


def duplicate_positions_by_job_entity_uid(
    positions: Sequence[Position],
) -> dict[tuple[str | None, str | None], int]:
    keys = [(p.job_id, entity_uid_from_position(p)) for p in positions]
    return _duplicate_keys(keys)


def duplicate_products_by_job_position_sku(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str, str], int]:
    keys = [
        (position_job_id.get(prod.position_id), prod.position_id, prod.sku or "")
        for prod in products
    ]
    return _duplicate_keys(keys)


def duplicate_evidence_by_scope(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str, str], int]:
    keys: list[tuple[str | None, str, str]] = []
    for ev in evidence_rows:
        pos_id = getattr(ev, "entity_id", None) or ""
        path = getattr(ev, "storage_path", None) or getattr(ev, "storage_key", None) or ""
        keys.append((position_job_id.get(pos_id), pos_id, str(path)))
    return _duplicate_keys(keys)


def duplicate_raw_labels(labels: Sequence[RawLabel]) -> dict[tuple[str | None, str, str, str], int]:
    keys = [
        (
            lb.job_id,
            lb.position_id or "",
            lb.group_key,
            (lb.source_reference or "").strip(),
        )
        for lb in labels
    ]
    return _duplicate_keys(keys)


def duplicate_normalized_labels(
    labels: Sequence[NormalizedLabel],
) -> dict[tuple[str | None, str, str, str], int]:
    keys = [
        (
            lb.job_id,
            lb.position_id or "",
            lb.group_key,
            (lb.canonical_sku or "").strip(),
        )
        for lb in labels
    ]
    return _duplicate_keys(keys)


def duplicate_final_counts(
    records: Sequence[FinalCountRecord],
) -> dict[tuple[str | None, str | None, str], int]:
    keys = [(rec.job_id, rec.position_id, rec.sku or "") for rec in records]
    return _duplicate_keys(keys)


# --- Semantic repetition (same business value on different position rows) -------


def repeated_products_by_job_sku(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str], int]:
    keys = [(position_job_id.get(prod.position_id), prod.sku or "") for prod in products]
    return _duplicate_keys(keys)


def repeated_evidence_by_job_path(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str], int]:
    keys: list[tuple[str | None, str]] = []
    for ev in evidence_rows:
        pos_id = getattr(ev, "entity_id", None) or ""
        path = getattr(ev, "storage_path", None) or getattr(ev, "storage_key", None) or ""
        keys.append((position_job_id.get(pos_id), str(path)))
    return _duplicate_keys(keys)


def repeated_raw_labels_by_source_reference(
    labels: Sequence[RawLabel],
) -> dict[tuple[str | None, str], int]:
    keys = [(lb.job_id, (lb.source_reference or "").strip()) for lb in labels]
    return _duplicate_keys(keys)


def repeated_normalized_labels_by_job_sku(
    labels: Sequence[NormalizedLabel],
) -> dict[tuple[str | None, str], int]:
    keys = [(lb.job_id, (lb.canonical_sku or "").strip()) for lb in labels]
    return _duplicate_keys(keys)


def repeated_final_counts_by_job_sku(
    records: Sequence[FinalCountRecord],
) -> dict[tuple[str | None, str], int]:
    keys = [(rec.job_id, (rec.sku or "").strip()) for rec in records]
    return _duplicate_keys(keys)
