"""Read-only domain snapshot verifier — Phase 3.3."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.domain.jobs.finalization_evidence import (
    DomainSnapshotVerdict,
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)


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
    """Inspect job-scoped rows for referential completeness — read-only."""

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
        stage_store: FinalizationStageStore | None = None,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_repo = product_repo
        self._evidence_repo = evidence_repo
        self._raw_label_repo = raw_label_repo
        self._normalized_label_repo = normalized_label_repo
        self._final_count_repo = final_count_repo
        self._stage_store = stage_store

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

        domain_stage = None
        if self._stage_store is not None:
            domain_stage = self._stage_store.get_stage(job_id, FinalizationStage.DOMAIN_RESULTS)

        inventory_id = aisle.inventory_id
        positions = list(self._position_repo.list_by_aisle(aisle_id, job_id=job_id))
        position_ids = {p.id for p in positions}

        products: list = []
        evidence: list = []
        for pos in positions:
            pos_products = list(self._product_repo.list_by_position(pos.id))
            products.extend(pos_products)
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

        counts = DomainSnapshotVerification(
            verdict=DomainSnapshotVerdict.INCOMPLETE,
            position_count=len(positions),
            product_count=len(products),
            evidence_count=len(evidence),
            raw_label_count=len(raw_labels),
            normalized_label_count=len(normalized),
            final_count_count=len(final_counts),
        )

        if not position_ids:
            return self._empty_scope_verdict(
                domain_stage=domain_stage,
                counts=counts,
                aisle_id=aisle_id,
                job_id=job_id,
            )

        for product in products:
            if product.position_id not in position_ids:
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.INCOMPLETE,
                    position_count=counts.position_count,
                    product_count=counts.product_count,
                    evidence_count=counts.evidence_count,
                    raw_label_count=counts.raw_label_count,
                    normalized_label_count=counts.normalized_label_count,
                    final_count_count=counts.final_count_count,
                    detail="product_position_out_of_scope",
                )

        products_by_position: dict[str, list] = defaultdict(list)
        for product in products:
            products_by_position[product.position_id].append(product)

        for pos_id in position_ids:
            if not products_by_position.get(pos_id):
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.INCOMPLETE,
                    position_count=counts.position_count,
                    product_count=counts.product_count,
                    evidence_count=counts.evidence_count,
                    raw_label_count=counts.raw_label_count,
                    normalized_label_count=counts.normalized_label_count,
                    final_count_count=counts.final_count_count,
                    detail="position_without_product",
                )

        for ev in evidence:
            if ev.entity_type != "position" or ev.entity_id not in position_ids:
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.INCOMPLETE,
                    position_count=counts.position_count,
                    product_count=counts.product_count,
                    evidence_count=counts.evidence_count,
                    raw_label_count=counts.raw_label_count,
                    normalized_label_count=counts.normalized_label_count,
                    final_count_count=counts.final_count_count,
                    detail="evidence_position_out_of_scope",
                )

        for raw_label in raw_labels:
            if raw_label.position_id and raw_label.position_id not in position_ids:
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.INCOMPLETE,
                    position_count=counts.position_count,
                    product_count=counts.product_count,
                    evidence_count=counts.evidence_count,
                    raw_label_count=counts.raw_label_count,
                    normalized_label_count=counts.normalized_label_count,
                    final_count_count=counts.final_count_count,
                    detail="raw_label_position_out_of_scope",
                )

        for normalized_label in normalized:
            if normalized_label.position_id and normalized_label.position_id not in position_ids:
                return DomainSnapshotVerification(
                    verdict=DomainSnapshotVerdict.INCOMPLETE,
                    position_count=counts.position_count,
                    product_count=counts.product_count,
                    evidence_count=counts.evidence_count,
                    raw_label_count=counts.raw_label_count,
                    normalized_label_count=counts.normalized_label_count,
                    final_count_count=counts.final_count_count,
                    detail="normalized_label_position_out_of_scope",
                )

        return DomainSnapshotVerification(
            verdict=DomainSnapshotVerdict.CONFIRMED_COMPLETE,
            position_count=counts.position_count,
            product_count=counts.product_count,
            evidence_count=counts.evidence_count,
            raw_label_count=counts.raw_label_count,
            normalized_label_count=counts.normalized_label_count,
            final_count_count=counts.final_count_count,
        )

    def _empty_scope_verdict(
        self,
        *,
        domain_stage,
        counts: DomainSnapshotVerification,
        aisle_id: str,
        job_id: str,
    ) -> DomainSnapshotVerification:
        if (
            domain_stage is not None
            and domain_stage.status == StageStatus.COMPLETED
            and domain_stage.evidence_level == EvidenceLevel.TRANSACTIONAL
        ):
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=counts.raw_label_count,
                normalized_label_count=counts.normalized_label_count,
                final_count_count=counts.final_count_count,
            )
        if domain_stage is not None and domain_stage.status == StageStatus.COMPLETED:
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.AMBIGUOUS,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=counts.raw_label_count,
                normalized_label_count=counts.normalized_label_count,
                final_count_count=counts.final_count_count,
                detail="empty_scope_without_transactional_evidence",
            )
        other_positions = list(self._position_repo.list_by_aisle(aisle_id))
        if any(getattr(p, "job_id", None) == job_id for p in other_positions):
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.AMBIGUOUS,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=counts.raw_label_count,
                normalized_label_count=counts.normalized_label_count,
                final_count_count=counts.final_count_count,
                detail="empty_scope_job_mismatch",
            )
        if other_positions:
            return DomainSnapshotVerification(
                verdict=DomainSnapshotVerdict.AMBIGUOUS,
                position_count=0,
                product_count=0,
                evidence_count=0,
                raw_label_count=counts.raw_label_count,
                normalized_label_count=counts.normalized_label_count,
                final_count_count=counts.final_count_count,
                detail="empty_scope_with_other_rows",
            )
        return DomainSnapshotVerification(
            verdict=DomainSnapshotVerdict.NOT_FOUND,
            position_count=0,
            product_count=0,
            evidence_count=0,
            raw_label_count=counts.raw_label_count,
            normalized_label_count=counts.normalized_label_count,
            final_count_count=counts.final_count_count,
            detail="no_domain_evidence",
        )
