"""Read-only domain snapshot verifier — Phase 3.3."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.domain.jobs.finalization_evidence import DomainSnapshotVerdict


@dataclass(frozen=True)
class DomainSnapshotVerification:
    verdict: DomainSnapshotVerdict
    position_count: int
    product_count: int
    evidence_count: int
    raw_label_count: int
    normalized_label_count: int
    final_count_count: int
    detail: str | None = None


class JobDomainResultVerifier:
    """Inspect job-scoped rows for completeness — read-only."""

    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        raw_label_repo: RawLabelRepository,
        normalized_label_repo: NormalizedLabelRepository,
        final_count_repo: FinalCountRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_repo = product_repo
        self._evidence_repo = evidence_repo
        self._raw_label_repo = raw_label_repo
        self._normalized_label_repo = normalized_label_repo
        self._final_count_repo = final_count_repo

    def verify(self, *, job_id: str, aisle_id: str) -> DomainSnapshotVerification:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.NOT_FOUND,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=0,
                normalized_label_count=0,
                final_count_count=0,
                detail="aisle_not_found",
            )

        inventory_id = aisle.inventory_id
        positions = list(self._position_repo.list_by_aisle(aisle_id, job_id=job_id))
        products: list = []
        evidence: list = []
        for pos in positions:
            products.extend(self._product_repo.list_by_position(pos.id))
            evidence.extend(self._evidence_repo.list_by_entity("position", pos.id))

        raw_labels = list(
            self._raw_label_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )
        normalized = list(
            self._normalized_label_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )
        final_counts = list(
            self._final_count_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )

        pos_n, prod_n, ev_n = len(positions), len(products), len(evidence)
        if pos_n != prod_n or prod_n != ev_n:
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.INCOMPLETE,
                position_count=pos_n,
                product_count=prod_n,
                evidence_count=ev_n,
                raw_label_count=len(raw_labels),
                normalized_label_count=len(normalized),
                final_count_count=len(final_counts),
                detail="position_product_evidence_mismatch",
            )

        if pos_n == 0:
            other_positions = list(self._position_repo.list_by_aisle(aisle_id))
            if any(getattr(p, "job_id", None) == job_id for p in other_positions):
                pass
            elif other_positions:
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.AMBIGUOUS,
                    position_count=0,
                    product_count=0,
                    evidence_count=0,
                    raw_label_count=len(raw_labels),
                    normalized_label_count=len(normalized),
                    final_count_count=len(final_counts),
                    detail="empty_scope_with_other_rows",
                )
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=len(raw_labels),
                normalized_label_count=len(normalized),
                final_count_count=len(final_counts),
            )

        return DomainSnapshotVerification(
            verdict=DomainSnapshotVerdict.CONFIRMED_COMPLETE,
            position_count=pos_n,
            product_count=prod_n,
            evidence_count=ev_n,
            raw_label_count=len(raw_labels),
            normalized_label_count=len(normalized),
            final_count_count=len(final_counts),
        )
