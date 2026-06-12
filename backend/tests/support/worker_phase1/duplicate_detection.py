"""Test-only duplicate detection by business keys for Phase 2 idempotency characterization."""

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


def position_keys_by_entity_uid(positions: Sequence[Position]) -> list[tuple[str | None, str | None]]:
    return [(p.job_id, entity_uid_from_position(p)) for p in positions]


def duplicate_positions_by_job_entity_uid(
    positions: Sequence[Position],
) -> dict[tuple[str | None, str | None], int]:
    return _duplicate_keys(position_keys_by_entity_uid(positions))


def product_keys(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> list[tuple[str | None, str, str]]:
    return [
        (position_job_id.get(prod.position_id), prod.position_id, prod.sku or "")
        for prod in products
    ]


def duplicate_products_by_job_position_sku(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str, str], int]:
    return _duplicate_keys(product_keys(products, position_job_id=position_job_id))


def product_keys_by_job_sku(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> list[tuple[str | None, str]]:
    return [(position_job_id.get(prod.position_id), prod.sku or "") for prod in products]


def duplicate_products_by_job_sku(
    products: Sequence[ProductRecord],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str], int]:
    """Semantic duplicate detection when each persist creates new position_ids."""
    return _duplicate_keys(product_keys_by_job_sku(products, position_job_id=position_job_id))


def evidence_keys(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> list[tuple[str | None, str, str]]:
    out: list[tuple[str | None, str, str]] = []
    for ev in evidence_rows:
        pos_id = getattr(ev, "entity_id", None) or ""
        path = getattr(ev, "storage_path", None) or getattr(ev, "storage_key", None) or ""
        out.append((position_job_id.get(pos_id), pos_id, str(path)))
    return out


def duplicate_evidence_by_scope(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str, str], int]:
    return _duplicate_keys(evidence_keys(evidence_rows, position_job_id=position_job_id))


def evidence_keys_by_job_path(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for ev in evidence_rows:
        pos_id = getattr(ev, "entity_id", None) or ""
        path = getattr(ev, "storage_path", None) or getattr(ev, "storage_key", None) or ""
        out.append((position_job_id.get(pos_id), str(path)))
    return out


def duplicate_evidence_by_job_path(
    evidence_rows: Sequence[Any],
    *,
    position_job_id: dict[str, str | None],
) -> dict[tuple[str | None, str], int]:
    return _duplicate_keys(evidence_keys_by_job_path(evidence_rows, position_job_id=position_job_id))


def raw_label_keys(labels: Sequence[RawLabel]) -> list[tuple[str | None, str | None, str]]:
    return [(lb.job_id, lb.position_id, lb.group_key) for lb in labels]


def duplicate_raw_labels(labels: Sequence[RawLabel]) -> dict[tuple[str | None, str | None, str], int]:
    return _duplicate_keys(raw_label_keys(labels))


def raw_label_keys_by_source_reference(
    labels: Sequence[RawLabel],
) -> list[tuple[str | None, str]]:
    return [(lb.job_id, (lb.source_reference or "").strip()) for lb in labels]


def duplicate_raw_labels_by_source_reference(
    labels: Sequence[RawLabel],
) -> dict[tuple[str | None, str], int]:
    """Semantic duplicate detection when each persist creates new position_ids."""
    return _duplicate_keys(raw_label_keys_by_source_reference(labels))


def normalized_label_keys(labels: Sequence[NormalizedLabel]) -> list[tuple[str | None, str, str]]:
    return [(lb.job_id, lb.position_id or "", lb.group_key) for lb in labels]


def duplicate_normalized_labels(
    labels: Sequence[NormalizedLabel],
) -> dict[tuple[str | None, str, str], int]:
    return _duplicate_keys(normalized_label_keys(labels))


def normalized_label_keys_by_sku(
    labels: Sequence[NormalizedLabel],
) -> list[tuple[str | None, str]]:
    return [(lb.job_id, (lb.canonical_sku or "").strip()) for lb in labels]


def duplicate_normalized_labels_by_sku(
    labels: Sequence[NormalizedLabel],
) -> dict[tuple[str | None, str], int]:
    """Detect duplicate normalized rows per SKU within a job (recompute reads all raw labels)."""
    return _duplicate_keys(normalized_label_keys_by_sku(labels))


def final_count_keys(records: Sequence[FinalCountRecord]) -> list[tuple[str | None, str | None, str]]:
    return [(rec.job_id, rec.position_id, rec.sku or "") for rec in records]


def duplicate_final_counts(
    records: Sequence[FinalCountRecord],
) -> dict[tuple[str | None, str | None, str], int]:
    return _duplicate_keys(final_count_keys(records))


def final_count_keys_by_sku(
    records: Sequence[FinalCountRecord],
) -> list[tuple[str | None, str]]:
    return [(rec.job_id, (rec.sku or "").strip()) for rec in records]


def duplicate_final_counts_by_sku(
    records: Sequence[FinalCountRecord],
) -> dict[tuple[str | None, str], int]:
    return _duplicate_keys(final_count_keys_by_sku(records))
