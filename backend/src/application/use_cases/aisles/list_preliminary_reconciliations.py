"""Read-only list + SQL aggregate metrics for preliminary reconciliations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.application.ports.preliminary_detection_reconciliation_repository import (
    PreliminaryDetectionReconciliationRepository,
)
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.use_cases.aisles.reconcile_preliminary_detections import (
    ReconciliationDisabledError,
)
from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)


@dataclass
class ListPreliminaryReconciliationsCommand:
    inventory_id: str
    aisle_id: str
    job_id: str | None = None
    preliminary_detection_id: str | None = None
    comparison_version: str | None = None
    outcome: str | None = None
    asset_id: str | None = None
    client_file_id: str | None = None
    parser_version: str | None = None
    detector_version: str | None = None
    comparable_only: bool | None = None
    compared_after: datetime | None = None
    compared_before: datetime | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class ReconciliationMetricsSummary:
    """Server-agreement proxies — not human ground-truth accuracy."""

    total_eligible_drafts: int
    total_reconciled: int
    total_pending: int
    total_not_comparable: int
    mapping_comparable: int
    code_comparable: int
    quantity_comparable: int
    code_match_count: int
    code_mismatch_count: int
    quantity_match_count: int
    quantity_mismatch_count: int
    local_only_count: int
    remote_only_count: int
    ambiguous_count: int
    both_unresolved_count: int
    comparability_rate: float | None
    server_code_agreement_rate: float | None
    quantity_agreement_rate: float | None
    local_only_rate: float | None
    remote_only_rate: float | None
    ambiguity_rate: float | None
    numerator_agreement: int
    denominator_comparable: int


@dataclass
class ListPreliminaryReconciliationsResult:
    items: Sequence[PreliminaryDetectionReconciliation]
    total: int
    metrics: ReconciliationMetricsSummary


def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 6)


def metrics_from_aggregate(agg: dict[str, int], *, eligible: int) -> ReconciliationMetricsSummary:
    mapping = int(agg.get("mapping_comparable", 0))
    code_match = int(agg.get("code_match_count", 0))
    code_comp = int(agg.get("code_comparable", 0)) or mapping
    qty_match = int(agg.get("quantity_match_count", 0))
    qty_comp = int(agg.get("quantity_comparable", 0))
    return ReconciliationMetricsSummary(
        total_eligible_drafts=eligible,
        total_reconciled=int(agg.get("total_reconciled", 0)),
        total_pending=int(agg.get("total_pending", 0)),
        total_not_comparable=int(agg.get("total_not_comparable", 0)),
        mapping_comparable=mapping,
        code_comparable=code_comp,
        quantity_comparable=qty_comp,
        code_match_count=code_match,
        code_mismatch_count=int(agg.get("code_mismatch_count", 0)),
        quantity_match_count=qty_match,
        quantity_mismatch_count=int(agg.get("quantity_mismatch_count", 0)),
        local_only_count=int(agg.get("local_only_count", 0)),
        remote_only_count=int(agg.get("remote_only_count", 0)),
        ambiguous_count=int(agg.get("ambiguous_count", 0)),
        both_unresolved_count=int(agg.get("both_unresolved_count", 0)),
        comparability_rate=_rate(mapping, max(eligible, int(agg.get("total_reconciled", 0)))),
        server_code_agreement_rate=_rate(code_match, code_comp),
        quantity_agreement_rate=_rate(qty_match, qty_comp),
        local_only_rate=_rate(int(agg.get("local_only_count", 0)), mapping),
        remote_only_rate=_rate(int(agg.get("remote_only_count", 0)), mapping),
        ambiguity_rate=_rate(int(agg.get("ambiguous_count", 0)), mapping),
        numerator_agreement=code_match,
        denominator_comparable=code_comp,
    )


class ListPreliminaryReconciliationsUseCase:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        reconciliation_repo: PreliminaryDetectionReconciliationRepository,
        enabled: bool,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._reconciliation_repo = reconciliation_repo
        self._enabled = enabled

    def execute(
        self, command: ListPreliminaryReconciliationsCommand
    ) -> ListPreliminaryReconciliationsResult:
        if not self._enabled:
            raise ReconciliationDisabledError()

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )

        items = self._reconciliation_repo.list_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            job_id=command.job_id,
            preliminary_detection_id=command.preliminary_detection_id,
            comparison_version=command.comparison_version,
            outcome=command.outcome,
            asset_id=command.asset_id,
            client_file_id=command.client_file_id,
            parser_version=command.parser_version,
            detector_version=command.detector_version,
            comparable_only=command.comparable_only,
            compared_after=command.compared_after,
            compared_before=command.compared_before,
            limit=max(1, min(command.limit, 500)),
            offset=max(0, command.offset),
        )
        total = self._reconciliation_repo.count_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            job_id=command.job_id,
            preliminary_detection_id=command.preliminary_detection_id,
            comparison_version=command.comparison_version,
            outcome=command.outcome,
            asset_id=command.asset_id,
            client_file_id=command.client_file_id,
            parser_version=command.parser_version,
            detector_version=command.detector_version,
            comparable_only=command.comparable_only,
            compared_after=command.compared_after,
            compared_before=command.compared_before,
        )
        agg = self._reconciliation_repo.aggregate_metrics(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            job_id=command.job_id,
            parser_version=command.parser_version,
            detector_version=command.detector_version,
        )
        eligible = int(agg.get("total_reconciled", 0)) + int(agg.get("total_pending", 0))
        metrics = metrics_from_aggregate(agg, eligible=eligible)
        return ListPreliminaryReconciliationsResult(items=items, total=total, metrics=metrics)
