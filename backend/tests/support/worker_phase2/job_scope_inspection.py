"""Inspect job-scoped persistence layers for Phase 2 characterization tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.domain.aisle.entities import Aisle
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)


@dataclass(frozen=True)
class JobScopeSnapshot:
    job_id: str
    position_ids: tuple[str, ...]
    product_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    raw_label_ids: tuple[str, ...]
    normalized_label_ids: tuple[str, ...]
    final_count_ids: tuple[str, ...]
    position_count: int
    product_count: int
    evidence_count: int
    raw_label_count: int
    normalized_label_count: int
    final_count_count: int


def assert_no_row_id_overlap(*row_id_groups: Sequence[str]) -> None:
    """Ensure persisted row id sets from different jobs do not overlap."""
    seen: set[str] = set()
    for group in row_id_groups:
        ids = set(group)
        assert not seen & ids, f"row id overlap detected: {seen & ids}"
        seen |= ids


def position_job_id_map(
    position_repo: PositionRepository,
    aisle_id: str,
    job_id: str,
) -> dict[str, str | None]:
    positions = list(position_repo.list_by_aisle(aisle_id, job_id=job_id))
    return {p.id: p.job_id for p in positions}


def products_for_job(
    position_repo: PositionRepository,
    product_repo: ProductRecordRepository,
    aisle_id: str,
    job_id: str,
) -> list[Any]:
    products: list[Any] = []
    for pos in position_repo.list_by_aisle(aisle_id, job_id=job_id):
        products.extend(product_repo.list_by_position(pos.id))
    return products


def evidence_for_job(
    position_repo: PositionRepository,
    evidence_repo: EvidenceRepository,
    aisle_id: str,
    job_id: str,
) -> list[Any]:
    rows: list[Any] = []
    for pos in position_repo.list_by_aisle(aisle_id, job_id=job_id):
        rows.extend(evidence_repo.list_by_entity("position", pos.id))
    return rows


def raw_labels_for_job(
    raw_repo: RawLabelRepository,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> list[Any]:
    return list(raw_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id))


def normalized_labels_for_job(
    norm_repo: MemoryNormalizedLabelRepository,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> list[Any]:
    return list(norm_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id))


def final_counts_for_job(
    final_repo: MemoryFinalCountRepository,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> list[Any]:
    return list(final_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id))


def snapshot_job_scope(
    *,
    position_repo: PositionRepository,
    product_repo: ProductRecordRepository,
    evidence_repo: EvidenceRepository,
    raw_repo: RawLabelRepository,
    norm_repo: MemoryNormalizedLabelRepository,
    final_repo: MemoryFinalCountRepository,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> JobScopeSnapshot:
    positions = list(position_repo.list_by_aisle(aisle_id, job_id=job_id))
    products = products_for_job(position_repo, product_repo, aisle_id, job_id)
    evidence = evidence_for_job(position_repo, evidence_repo, aisle_id, job_id)
    raw_labels = raw_labels_for_job(raw_repo, inventory_id, aisle_id, job_id)
    norm_labels = normalized_labels_for_job(norm_repo, inventory_id, aisle_id, job_id)
    finals = final_counts_for_job(final_repo, inventory_id, aisle_id, job_id)
    return JobScopeSnapshot(
        job_id=job_id,
        position_ids=tuple(p.id for p in positions),
        product_ids=tuple(p.id for p in products),
        evidence_ids=tuple(e.id for e in evidence),
        raw_label_ids=tuple(r.id for r in raw_labels),
        normalized_label_ids=tuple(n.id for n in norm_labels),
        final_count_ids=tuple(f.id for f in finals),
        position_count=len(positions),
        product_count=len(products),
        evidence_count=len(evidence),
        raw_label_count=len(raw_labels),
        normalized_label_count=len(norm_labels),
        final_count_count=len(finals),
    )


def operational_job_id_for_aisle(aisle: Aisle | None) -> str | None:
    if aisle is None or not aisle.operational_job_id:
        return None
    return str(aisle.operational_job_id).strip() or None
