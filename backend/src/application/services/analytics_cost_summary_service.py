"""Aggregate LLM processing cost and counted quantity for the unified analytics dashboard."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.application.dto.analytics_cost_dto import (
    AnalyticsCostByAisleDTO,
    AnalyticsCostByCaptureStatusDTO,
    AnalyticsCostByInventoryDTO,
    AnalyticsCostByProviderModelDTO,
    AnalyticsCostSummaryDTO,
    AnalyticsCostSummaryFilters,
    AnalyticsCostSummaryScopeDTO,
    AnalyticsCostTotalsDTO,
)
from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.analytics_aggregation_core import _ts_in_range
from src.application.services.analytics_cost_counted_quantity import (
    AnalyticsCostCountedQuantityService,
)
from src.application.services.analytics_cost_snapshot_parser import (
    ParsedCostSnapshot,
    parse_llm_cost_snapshot,
)
from src.application.services.analytics_cost_warnings import (
    COST_PER_UNIT_NOT_AVAILABLE,
    COST_SNAPSHOT_MISSING_FOR_SOME_JOBS,
    COUNTED_QUANTITY_IS_OPERATIONAL_CURRENT_STATE,
    DATE_RANGE_CAPPED,
    LEGACY_JOBS_WITHOUT_COST,
    PARSER_WARNING_TO_ENDPOINT,
    PARTIAL_COST_CAPTURE_PRESENT,
    PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE,
)
from src.application.services.analytics_query_service import validate_analytics_filters_scope
from src.application.services.billable_job_cost_aggregation import (
    BILLABLE_TERMINAL_STATUSES,
    billable_cost_for_job,
)
from src.application.services.observability_metrics_service import (
    AISLE_TARGET,
    METRICS_JOB_LIMIT,
    PROCESS_AISLE_JOB_TYPE,
    ObservabilityMetricsFilters,
    _client_supplier_for_job,
    _h4_snapshot,
    _passes_filters,
    _provider_model_for_job,
    resolve_metrics_time_range,
)
from src.application.use_cases.shared.benchmark_compare_support import (
    job_execution_duration_seconds,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

_TERMINAL = BILLABLE_TERMINAL_STATUSES


@dataclass
class _Bucket:
    jobs_total: int = 0
    jobs_with_cost: int = 0
    jobs_without_cost: int = 0
    jobs_with_exact_cost: int = 0
    jobs_with_estimated_cost: int = 0
    jobs_with_partial_cost: int = 0
    jobs_with_unavailable_cost: int = 0
    jobs_with_missing_cost: int = 0
    cost_sum: Decimal = field(default_factory=lambda: Decimal("0"))
    has_cost: bool = False
    execution_seconds: list[float] = field(default_factory=list)


def _cost_per_unit(total_cost: Decimal | None, quantity: int | None) -> Decimal | None:
    if total_cost is None or quantity is None or quantity <= 0:
        return None
    return total_cost / Decimal(quantity)


def _decimal_or_none(value: Decimal, *, has: bool) -> Decimal | None:
    return value if has else None


def _avg_seconds(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _collect_parser_warnings(parsed: ParsedCostSnapshot, warnings: set[str]) -> None:
    for code in parsed.warnings:
        mapped = PARSER_WARNING_TO_ENDPOINT.get(code)
        if mapped:
            warnings.add(mapped)


class AnalyticsCostSummaryService:
    """Read-only LLM cost aggregates from persisted per-job ``llm_cost_snapshot`` rows."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        counted_quantity_service: AnalyticsCostCountedQuantityService,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._quantity = counted_quantity_service

    def validate_scope(self, filters: AnalyticsCostSummaryFilters) -> None:
        if filters.aisle_id and filters.inventory_id:
            validate_analytics_filters_scope(
                AnalyticsFilters(
                    date_from=None,
                    date_to=None,
                    inventory_id=filters.inventory_id,
                    aisle_id=filters.aisle_id,
                ),
                self._aisle_repo,
            )

    def build(self, filters: AnalyticsCostSummaryFilters) -> AnalyticsCostSummaryDTO:
        self.validate_scope(filters)
        warnings: set[str] = set()

        jobs = list(
            self._job_repo.list_jobs_for_metrics_by_finished_at(
                finished_from=filters.finished_from,
                finished_to=filters.finished_to,
                job_type=PROCESS_AISLE_JOB_TYPE,
                target_type=AISLE_TARGET,
                limit=METRICS_JOB_LIMIT,
            )
        )
        if len(jobs) >= METRICS_JOB_LIMIT:
            warnings.add(DATE_RANGE_CAPPED)

        scoped_jobs = self._filter_jobs(jobs, filters)
        job_aisle_ids = {
            str(j.target_id).strip()
            for j in scoped_jobs
            if j.target_type == AISLE_TARGET and j.target_id
        }

        quantity_scope = self._quantity.compute(
            inventory_id=filters.inventory_id,
            aisle_id=filters.aisle_id,
            job_aisle_ids=job_aisle_ids,
        )
        warnings.update(quantity_scope.warnings)

        totals_bucket = _Bucket()
        by_pm: dict[tuple[str | None, str | None], _Bucket] = defaultdict(_Bucket)
        by_inv: dict[str, _Bucket] = defaultdict(_Bucket)
        by_aisle: dict[str, _Bucket] = defaultdict(_Bucket)
        by_capture: dict[str, _Bucket] = defaultdict(_Bucket)

        inv_names: dict[str, str | None] = {}
        aisle_meta: dict[str, tuple[str, str | None, str | None]] = {}

        for job in scoped_jobs:
            aisle_id = str(job.target_id).strip() if job.target_id else ""
            aisle = self._aisle_repo.get_by_id(aisle_id) if aisle_id else None
            inventory_id = aisle.inventory_id if aisle else ""
            if aisle and aisle_id not in aisle_meta:
                inv = self._inventory_repo.get_by_id(inventory_id)
                inv_names.setdefault(inventory_id, inv.name if inv else None)
                aisle_meta[aisle_id] = (inventory_id, inv.name if inv else None, aisle.code)

            parsed = parse_llm_cost_snapshot(job.result_json if isinstance(job.result_json, dict) else None)
            _collect_parser_warnings(parsed, warnings)
            duration = job_execution_duration_seconds(job)

            self._accumulate(totals_bucket, job, parsed, duration)
            prov, model = _provider_model_for_job(
                job, _h4_snapshot(job.result_json if isinstance(job.result_json, dict) else None)
            )
            self._accumulate(by_pm[(prov, model)], job, parsed, duration)
            if inventory_id:
                self._accumulate(by_inv[inventory_id], job, parsed, duration)
            if aisle_id:
                self._accumulate(by_aisle[aisle_id], job, parsed, duration)
            self._accumulate(by_capture[parsed.capture_status], job, parsed, duration)

        if totals_bucket.jobs_with_cost < totals_bucket.jobs_total:
            warnings.add(COST_SNAPSHOT_MISSING_FOR_SOME_JOBS)
        if totals_bucket.jobs_with_partial_cost:
            warnings.add(PARTIAL_COST_CAPTURE_PRESENT)
        if totals_bucket.jobs_with_missing_cost:
            warnings.add(LEGACY_JOBS_WITHOUT_COST)

        totals_dto = self._totals_to_dto(totals_bucket, quantity_scope.total_counted_quantity)
        if totals_dto.total_counted_quantity is not None:
            warnings.add(COUNTED_QUANTITY_IS_OPERATIONAL_CURRENT_STATE)
        if totals_dto.cost_per_counted_unit is None and totals_dto.total_cost is not None:
            warnings.add(COST_PER_UNIT_NOT_AVAILABLE)

        if by_pm:
            warnings.add(PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE)

        scope = AnalyticsCostSummaryScopeDTO(
            date_from=filters.finished_from.date().isoformat(),
            date_to=filters.finished_to.date().isoformat(),
            inventory_id=filters.inventory_id,
            aisle_id=filters.aisle_id,
            client_id=filters.client_id,
            client_supplier_id=filters.client_supplier_id,
            provider_name=filters.provider_name,
            model_name=filters.model_name,
        )

        return AnalyticsCostSummaryDTO(
            scope=scope,
            totals=totals_dto,
            by_provider_model=[
                AnalyticsCostByProviderModelDTO(
                    provider_name=k[0],
                    model_name=k[1],
                    jobs_total=b.jobs_total,
                    jobs_with_cost=b.jobs_with_cost,
                    total_cost=_decimal_or_none(b.cost_sum, has=b.has_cost),
                    total_counted_quantity=None,
                    cost_per_counted_unit=None,
                    average_execution_time_seconds=_avg_seconds(b.execution_seconds),
                )
                for k, b in sorted(by_pm.items(), key=lambda x: (-x[1].jobs_total, x[0][0] or "", x[0][1] or ""))
            ],
            by_inventory=[
                AnalyticsCostByInventoryDTO(
                    inventory_id=inv_id,
                    inventory_name=inv_names.get(inv_id),
                    jobs_total=b.jobs_total,
                    jobs_with_cost=b.jobs_with_cost,
                    total_cost=_decimal_or_none(b.cost_sum, has=b.has_cost),
                    total_counted_quantity=quantity_scope.by_inventory_id.get(inv_id),
                    cost_per_counted_unit=_cost_per_unit(
                        _decimal_or_none(b.cost_sum, has=b.has_cost),
                        quantity_scope.by_inventory_id.get(inv_id),
                    ),
                    total_execution_time_seconds=sum(b.execution_seconds) if b.execution_seconds else None,
                )
                for inv_id, b in sorted(by_inv.items(), key=lambda x: (-x[1].jobs_total, x[0]))
            ],
            by_aisle=[
                AnalyticsCostByAisleDTO(
                    inventory_id=aisle_meta.get(aid, ("", None, None))[0],
                    inventory_name=aisle_meta.get(aid, ("", None, None))[1],
                    aisle_id=aid,
                    aisle_code=aisle_meta.get(aid, ("", None, None))[2],
                    jobs_total=b.jobs_total,
                    jobs_with_cost=b.jobs_with_cost,
                    total_cost=_decimal_or_none(b.cost_sum, has=b.has_cost),
                    total_counted_quantity=quantity_scope.by_aisle_id.get(aid),
                    cost_per_counted_unit=_cost_per_unit(
                        _decimal_or_none(b.cost_sum, has=b.has_cost),
                        quantity_scope.by_aisle_id.get(aid),
                    ),
                    total_execution_time_seconds=sum(b.execution_seconds) if b.execution_seconds else None,
                )
                for aid, b in sorted(by_aisle.items(), key=lambda x: (-x[1].jobs_total, x[0]))
            ],
            by_capture_status=[
                AnalyticsCostByCaptureStatusDTO(
                    capture_status=status,
                    jobs_total=b.jobs_total,
                    total_cost=_decimal_or_none(b.cost_sum, has=b.has_cost),
                )
                for status, b in sorted(
                    by_capture.items(),
                    key=lambda x: (
                        ["exact", "estimated", "partial", "unavailable", "missing"].index(x[0])
                        if x[0] in {"exact", "estimated", "partial", "unavailable", "missing"}
                        else 99
                    ),
                )
            ],
            warnings=sorted(warnings),
        )

    def _filter_jobs(self, jobs: list[Job], filters: AnalyticsCostSummaryFilters) -> list[Job]:
        # Historical cost scope: include ALL aisles (active and inactive) so soft-deactivated
        # aisles remain in LLM/job cost history. Do not filter by is_active here.
        allowed_aisle: set[str] | None = None
        if filters.aisle_id:
            allowed_aisle = {filters.aisle_id}
        elif filters.inventory_id:
            allowed_aisle = {a.id for a in self._aisle_repo.list_by_inventory(filters.inventory_id)}

        obs_filters = ObservabilityMetricsFilters(
            created_from=filters.finished_from,
            created_to=filters.finished_to,
            client_id=filters.client_id,
            client_supplier_id=filters.client_supplier_id,
            provider_name=filters.provider_name,
            model_name=filters.model_name,
        )

        out: list[Job] = []
        for job in jobs:
            if job.target_type != AISLE_TARGET or not job.target_id:
                continue
            if job.status not in _TERMINAL:
                continue
            if job.finished_at is None:
                continue
            if not _ts_in_range(job.finished_at, filters.finished_from, filters.finished_to):
                continue
            aisle_id = str(job.target_id).strip()
            if allowed_aisle is not None and aisle_id not in allowed_aisle:
                continue
            snap = _h4_snapshot(job.result_json if isinstance(job.result_json, dict) else None)
            client_id, supplier_id = _client_supplier_for_job(
                job, snap, self._aisle_repo, self._inventory_repo
            )
            prov, model = _provider_model_for_job(job, snap)
            if not _passes_filters(
                client_id=client_id,
                supplier_id=supplier_id,
                provider=prov,
                model=model,
                filters=obs_filters,
            ):
                continue
            out.append(job)
        return out

    def _accumulate(
        self,
        bucket: _Bucket,
        job: Job,
        parsed: ParsedCostSnapshot,
        duration: float | None,
    ) -> None:
        bucket.jobs_total += 1
        if parsed.capture_status == "exact":
            bucket.jobs_with_exact_cost += 1
        elif parsed.capture_status == "estimated":
            bucket.jobs_with_estimated_cost += 1
        elif parsed.capture_status == "partial":
            bucket.jobs_with_partial_cost += 1
        elif parsed.capture_status == "unavailable":
            bucket.jobs_with_unavailable_cost += 1
        else:
            bucket.jobs_with_missing_cost += 1

        if duration is not None:
            bucket.execution_seconds.append(duration)

        # Money totals use the shared billable policy (not a local re-definition).
        amount = billable_cost_for_job(job)
        if amount is not None:
            bucket.jobs_with_cost += 1
            bucket.cost_sum += amount
            bucket.has_cost = True
        else:
            bucket.jobs_without_cost += 1

    def _totals_to_dto(self, bucket: _Bucket, total_quantity: int | None) -> AnalyticsCostTotalsDTO:
        total_cost = _decimal_or_none(bucket.cost_sum, has=bucket.has_cost)
        exec_total = sum(bucket.execution_seconds) if bucket.execution_seconds else None
        return AnalyticsCostTotalsDTO(
            jobs_total=bucket.jobs_total,
            jobs_with_cost=bucket.jobs_with_cost,
            jobs_without_cost=bucket.jobs_without_cost,
            jobs_with_exact_cost=bucket.jobs_with_exact_cost,
            jobs_with_estimated_cost=bucket.jobs_with_estimated_cost,
            jobs_with_partial_cost=bucket.jobs_with_partial_cost,
            jobs_with_unavailable_cost=bucket.jobs_with_unavailable_cost,
            jobs_with_missing_cost=bucket.jobs_with_missing_cost,
            total_cost=total_cost,
            total_counted_quantity=total_quantity,
            cost_per_counted_unit=_cost_per_unit(total_cost, total_quantity),
            total_execution_time_seconds=exec_total,
            average_execution_time_seconds=_avg_seconds(bucket.execution_seconds),
        )


def resolve_cost_summary_time_range(
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[datetime, datetime]:
    """Same window rules as observability metrics; cost rows filter on ``finished_at``."""
    return resolve_metrics_time_range(date_from, date_to)
