"""
In-memory analytics — aggregates from v3 repositories (no SQL).

Processing success uses ``JobRepository.list_all_jobs()`` (same bulk read as SQL analytics).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Dict, List, Optional

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
from src.application.dto.analytics_dto import (
    AnalyticsFilters,
    AnalyticsSummaryDTO,
    AnalyticsTrendsDTO,
    AisleIssueRowDTO,
    InventoryPerformanceRowDTO,
    ManualInterventionBreakdownDTO,
    ManualInterventionCategoryDTO,
    QualityPatternRowDTO,
    TrendPointDTO,
)
from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.analytics_aggregation_core import (
    build_inventory_metric_rates,
    build_summary_metrics,
    compute_average_review_time_seconds,
    compute_manual_intervention_breakdown,
    compute_processing_success_rate,
    compute_review_outcome_counts,
    correction_action,
    day_span_inclusive,
    issue_bucket_for_position,
    most_common_issue_for_counts,
    position_in_scope,
    settling_action,
    active_position,
    is_invalid_traceability,
    is_low_confidence,
    unidentified_product,
    processed_position,
    review_action_in_period,
    InventoryMetricInputs,
    SummaryMetricInputs,
)
from src.domain.jobs.entities import JobStatus
from src.domain.positions.entities import Position, PositionReviewResolution, PositionStatus
from src.domain.products.entities import ProductRecord


class MemoryAnalyticsRepository(AnalyticsRepository):
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        review_action_repo: ReviewActionRepository,
        job_repo: JobRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._review_action_repo = review_action_repo
        self._job_repo = job_repo

    def _primary_by_position(
        self,
        positions: Dict[str, Position],
    ) -> Dict[str, Optional[ProductRecord]]:
        """Resolve display-primary product once per position set."""
        return {
            pid: select_display_primary_product(self._product_record_repo.list_by_position(pid))
            for pid in positions
        }

    def _collect(
        self, filters: AnalyticsFilters
    ) -> tuple[Dict[str, Position], Dict[str, str], Dict[str, str], List]:
        """Positions in scope, aisle->inventory, position_id->aisle_id, all review actions."""
        aisle_to_inventory: Dict[str, str] = {}
        position_to_aisle: Dict[str, str] = {}
        positions: Dict[str, Position] = {}
        inventories = self._inventory_repo.list_all()
        for inv in inventories:
            if filters.inventory_id and inv.id != filters.inventory_id:
                continue
            for aisle in self._aisle_repo.list_by_inventory(inv.id):
                if filters.aisle_id and aisle.id != filters.aisle_id:
                    continue
                aisle_to_inventory[aisle.id] = inv.id
                for pos in self._position_repo.list_by_aisle(
                    aisle.id, page=1, page_size=100000, sort_by="id", sort_dir="asc"
                ):
                    position_to_aisle[pos.id] = aisle.id
                    if not position_in_scope(pos, aisle.id, inv.id, aisle_to_inventory, filters):
                        continue
                    positions[pos.id] = pos
        actions: List = []
        from src.infrastructure.repositories.memory_review_action_repository import (  # noqa: PLC0415
            MemoryReviewActionRepository,
        )

        if isinstance(self._review_action_repo, MemoryReviewActionRepository):
            raw_actions = list(self._review_action_repo._store)  # type: ignore[attr-defined]
        else:
            raw_actions = []
            for pid in positions:
                raw_actions.extend(self._review_action_repo.list_by_position(pid))
        pids = set(positions.keys())
        actions = [a for a in raw_actions if a.position_id in pids]
        return positions, aisle_to_inventory, position_to_aisle, actions

    def get_summary(self, filters: AnalyticsFilters) -> AnalyticsSummaryDTO:
        notes: List[str] = []
        positions, aisle_to_inv, pos_to_aisle, actions = self._collect(filters)
        active = {pid: p for pid, p in positions.items() if active_position(p)}
        primary_by_position = self._primary_by_position(active)
        review_outcomes = compute_review_outcome_counts(actions, filters.date_from, filters.date_to)
        invalid_n = sum(
            1
            for pid, p in active.items()
            if is_invalid_traceability(p, primary_by_position.get(pid))
        )
        total_positions = len(active)
        processed_positions = sum(1 for p in active.values() if processed_position(p))

        allowed_aisles = set(aisle_to_inv.keys())
        if filters.aisle_id:
            allowed_aisles &= {filters.aisle_id}
        jobs_list = list(self._job_repo.list_all_jobs())
        proc = compute_processing_success_rate(
            jobs_list, filters.date_from, filters.date_to, allowed_aisles
        )

        avg_sec = compute_average_review_time_seconds(positions, actions, filters.date_from, filters.date_to)
        span = day_span_inclusive(filters.date_from, filters.date_to)
        rpd = (
            review_outcomes.settling_actions_count / span
            if review_outcomes.settling_actions_count
            else None
        )
        if filters.date_from is None or filters.date_to is None:
            notes.append(
                "Date range open-ended: settling_actions_per_day uses a 1-day divisor; "
                "set date_from and date_to for meaningful per-day rates."
            )
        notes.append(
            "Current-state metrics use entity scope; date filters apply only to review-action and job-based metrics."
        )
        return build_summary_metrics(
            SummaryMetricInputs(
                total_positions_in_scope=total_positions,
                processed_positions_count=processed_positions,
                reviewed_positions_count=review_outcomes.reviewed_positions_count,
                auto_accepted_positions_count=review_outcomes.auto_accepted_positions_count,
                manually_corrected_positions_count=review_outcomes.manually_corrected_positions_count,
                operator_marked_unknown_positions_count=review_outcomes.operator_marked_unknown_positions_count,
                unidentified_product_positions_count=sum(
                    1 for pid in active if unidentified_product(primary_by_position.get(pid))
                ),
                invalid_traceability_positions_count=invalid_n,
                processing_success_rate=proc,
                average_review_time_seconds=avg_sec,
                settling_actions_per_day=rpd,
                settling_actions_count=review_outcomes.settling_actions_count,
                period_day_count=span,
                notes=notes,
            )
        )

    def get_trends(self, filters: AnalyticsFilters) -> AnalyticsTrendsDTO:
        if filters.date_from is None or filters.date_to is None:
            return AnalyticsTrendsDTO()
        positions, _, _, actions = self._collect(
            AnalyticsFilters(
                date_from=None,
                date_to=None,
                inventory_id=filters.inventory_id,
                aisle_id=filters.aisle_id,
            )
        )
        pids = set(positions.keys())

        by_day_rev: Dict[str, List] = defaultdict(list)
        for ra in actions:
            if ra.position_id not in pids or not settling_action(ra):
                continue
            if not review_action_in_period(ra, filters.date_from, filters.date_to):
                continue
            d = ra.created_at.date().isoformat()
            by_day_rev[d].append(ra)

        reviewed_series: List[TrendPointDTO] = []
        correction_series: List[TrendPointDTO] = []
        for d in sorted(by_day_rev.keys()):
            day_actions = by_day_rev[d]
            outcomes = compute_review_outcome_counts(day_actions, None, None)
            s = outcomes.settling_actions_count
            reviewed_series.append(
                TrendPointDTO(period=d, reviewed_results=s, correction_rate=None, processing_success_rate=None)
            )
            correction_series.append(
                TrendPointDTO(
                    period=d,
                    reviewed_results=s,
                    correction_rate=(
                        outcomes.manually_corrected_positions_count / outcomes.reviewed_positions_count
                        if outcomes.reviewed_positions_count
                        else None
                    ),
                    processing_success_rate=None,
                )
            )

        proc_series: List[TrendPointDTO] = []
        jobs_list = list(self._job_repo.list_all_jobs())
        _, aisle_to_inv, _, _ = self._collect(filters)
        allowed_aisles = set(aisle_to_inv.keys())
        if filters.aisle_id:
            allowed_aisles &= {filters.aisle_id}
        from src.application.services.analytics_aggregation_core import _ts_in_range

        by_day_job: Dict[str, list] = defaultdict(lambda: [0, 0])
        for j in jobs_list:
            if j.target_type != "aisle" or j.target_id not in allowed_aisles:
                continue
            if not _ts_in_range(j.updated_at, filters.date_from, filters.date_to):
                continue
            if j.status not in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                continue
            dkey = j.updated_at.date().isoformat()
            ok, fail = by_day_job[dkey]
            if j.status == JobStatus.SUCCEEDED:
                ok += 1
            else:
                fail += 1
            by_day_job[dkey] = [ok, fail]
        for dkey in sorted(by_day_job.keys()):
            ok_n, fail_n = by_day_job[dkey]
            tot = ok_n + fail_n
            pr = (ok_n / tot) if tot else None
            proc_series.append(
                TrendPointDTO(
                    period=dkey,
                    reviewed_results=tot,
                    correction_rate=None,
                    processing_success_rate=pr,
                )
            )

        return AnalyticsTrendsDTO(
            reviewed_results_over_time=reviewed_series,
            correction_rate_over_time=correction_series,
            processing_success_over_time=proc_series,
        )

    def get_inventory_performance(self, filters: AnalyticsFilters) -> List[InventoryPerformanceRowDTO]:
        out: List[InventoryPerformanceRowDTO] = []
        for inv in self._inventory_repo.list_all():
            if filters.inventory_id and inv.id != filters.inventory_id:
                continue
            inv_filter = AnalyticsFilters(
                date_from=filters.date_from,
                date_to=filters.date_to,
                inventory_id=inv.id,
                aisle_id=None,
            )
            positions, _, _, actions = self._collect(inv_filter)
            active_list = [p for p in positions.values() if active_position(p)]
            primary_by_position = self._primary_by_position(positions)
            aisles = self._aisle_repo.list_by_inventory(inv.id)
            if filters.aisle_id:
                aisles = [a for a in aisles if a.id == filters.aisle_id]
            total_aisles = len(aisles)
            total_pos = len(active_list)
            if total_aisles == 0 and total_pos == 0:
                continue
            processed_n = sum(1 for p in active_list if processed_position(p))
            invalid_n = sum(
                1
                for p in active_list
                if is_invalid_traceability(p, primary_by_position.get(p.id))
            )
            conf_vals = [p.confidence for p in active_list]
            avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else None

            review_outcomes = compute_review_outcome_counts(actions, filters.date_from, filters.date_to)

            aisle_ids = {a.id for a in aisles}
            jobs_list = list(self._job_repo.list_all_jobs())
            proc = compute_processing_success_rate(
                jobs_list, filters.date_from, filters.date_to, aisle_ids
            )
            avg_review_sec = compute_average_review_time_seconds(
                positions, actions, filters.date_from, filters.date_to
            )
            metric_rates = build_inventory_metric_rates(
                InventoryMetricInputs(
                    total_positions_in_scope=total_pos,
                    processed_positions_count=processed_n,
                    reviewed_positions_count=review_outcomes.reviewed_positions_count,
                    auto_accepted_positions_count=review_outcomes.auto_accepted_positions_count,
                    manually_corrected_positions_count=review_outcomes.manually_corrected_positions_count,
                    operator_marked_unknown_positions_count=review_outcomes.operator_marked_unknown_positions_count,
                    unidentified_product_positions_count=sum(
                        1 for p in active_list if unidentified_product(primary_by_position.get(p.id))
                    ),
                    invalid_traceability_positions_count=invalid_n,
                    avg_confidence=avg_conf,
                    processing_success_rate=proc,
                    average_review_time_seconds=avg_review_sec,
                )
            )

            created = inv.created_at if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=timezone.utc)
            out.append(
                InventoryPerformanceRowDTO(
                    inventory_id=inv.id,
                    inventory_name=inv.name,
                    inventory_created_at=created,
                    total_aisles=total_aisles,
                    aisles_count=total_aisles,
                    total_positions=total_pos,
                    positions_count=total_pos,
                    processed_positions=processed_n,
                    processed_count=processed_n,
                    review_rate=metric_rates["review_rate"],
                    correction_rate=metric_rates["correction_rate"],
                    auto_acceptance_rate=metric_rates["auto_acceptance_rate"],
                    manual_correction_rate=metric_rates["manual_correction_rate"],
                    operator_marked_unknown_rate=metric_rates["operator_marked_unknown_rate"],
                    unidentified_product_rate=metric_rates["unidentified_product_rate"],
                    unknown_rate=metric_rates["unknown_rate"],
                    invalid_traceability_rate=metric_rates["invalid_traceability_rate"],
                    avg_confidence=metric_rates["avg_confidence"],
                    processing_success_rate=metric_rates["processing_success_rate"],
                    average_review_time_minutes=metric_rates["average_review_time_minutes"],
                )
            )
        return sorted(out, key=lambda r: r.inventory_name.lower())

    def get_aisle_issues(self, filters: AnalyticsFilters) -> List[AisleIssueRowDTO]:
        rows: List[AisleIssueRowDTO] = []
        positions, _, pos_to_aisle, _ = self._collect(filters)
        primary_by_position = self._primary_by_position(positions)
        by_aisle: Dict[str, List[Position]] = {}
        meta: Dict[str, tuple] = {}
        for inv in self._inventory_repo.list_all():
            if filters.inventory_id and inv.id != filters.inventory_id:
                continue
            for aisle in self._aisle_repo.list_by_inventory(inv.id):
                if filters.aisle_id and aisle.id != filters.aisle_id:
                    continue
                meta[aisle.id] = (aisle.code, inv.id, inv.name)
                by_aisle.setdefault(aisle.id, [])
        for pos in positions.values():
            aid = pos_to_aisle.get(pos.id)
            if aid and aid in by_aisle:
                by_aisle[aid].append(pos)
        for aisle_id, plist in by_aisle.items():
            if not plist:
                continue
            code, inventory_id, inventory_name = meta[aisle_id]
            needs_r = sum(1 for p in plist if p.needs_review)
            corrected_c = sum(1 for p in plist if p.status == PositionStatus.CORRECTED)
            operator_marked_unknown_c = sum(
                1 for p in plist if p.review_resolution == PositionReviewResolution.UNKNOWN
            )
            unidentified_product_c = sum(
                1 for p in plist if unidentified_product(primary_by_position.get(p.id))
            )
            manual_corrections_c = sum(
                1
                for p in plist
                if p.review_resolution in (
                    PositionReviewResolution.QTY_CORRECTED,
                    PositionReviewResolution.SKU_CORRECTED,
                )
            )
            invalid_tr = sum(
                1
                for p in plist
                if is_invalid_traceability(p, primary_by_position.get(p.id))
            )
            low_conf = sum(1 for p in plist if is_low_confidence(p))
            bucket_counts: Dict[str, int] = {}
            for p in plist:
                b = issue_bucket_for_position(p, primary_by_position.get(p.id))
                bucket_counts[b] = bucket_counts.get(b, 0) + 1
            common = most_common_issue_for_counts(bucket_counts)
            rows.append(
                AisleIssueRowDTO(
                    aisle_id=aisle_id,
                    aisle_code=code,
                    inventory_id=inventory_id,
                    inventory_name=inventory_name,
                    total_results=len(plist),
                    needs_review_count=needs_r,
                    corrected_count=corrected_c,
                    operator_marked_unknown_count=operator_marked_unknown_c,
                    unidentified_product_count=unidentified_product_c,
                    unknown_count=operator_marked_unknown_c,
                    manual_corrections_count=manual_corrections_c,
                    invalid_traceability_count=invalid_tr,
                    low_confidence_count=low_conf,
                    most_common_issue=common,
                )
            )
        return sorted(rows, key=lambda r: (-r.needs_review_count, -r.total_results))

    def get_quality_patterns(self, filters: AnalyticsFilters) -> List[QualityPatternRowDTO]:
        positions, _, _, _ = self._collect(filters)
        primary_by_position = self._primary_by_position(positions)
        counts: Dict[str, int] = {}
        for p in positions.values():
            if not active_position(p):
                continue
            b = issue_bucket_for_position(p, primary_by_position.get(p.id))
            counts[b] = counts.get(b, 0) + 1
        total = sum(counts.values()) or 0
        display = {
            "unidentified_product": "Unidentified product",
            "invalid_traceability": "Invalid traceability",
            "missing_evidence": "Missing evidence",
            "quantity_zero": "Zero canonical quantity",
            "low_confidence": "Low confidence",
            "pending_review": "Pending review",
            "ok": "No primary issue",
        }
        notes_map = {
            "unidentified_product": "Display-primary product SKU is persisted as UNKNOWN",
            "invalid_traceability": "Canonical traceability status resolved as invalid",
            "missing_evidence": "No primary evidence id",
            "quantity_zero": "Canonical final quantity resolved as 0 (product record when available; aggregated rows may fall back to snapshot)",
            "low_confidence": f"confidence < {LOW_CONFIDENCE_THRESHOLD} (operational threshold)",
            "pending_review": "needs_review flag set",
            "ok": "Did not match higher-priority buckets",
        }
        out: List[QualityPatternRowDTO] = []
        for b, c in sorted(counts.items(), key=lambda x: -x[1]):
            pct = (c / total) if total else None
            out.append(
                QualityPatternRowDTO(
                    issue_type=display.get(b, b),
                    count=c,
                    percentage=pct,
                    notes=notes_map.get(b),
                )
            )
        return out

    def get_manual_intervention_breakdown(
        self, filters: AnalyticsFilters
    ) -> ManualInterventionBreakdownDTO:
        positions, _, _, actions = self._collect(filters)
        active_ids = {pid for pid, pos in positions.items() if active_position(pos)}
        scoped_actions = [a for a in actions if a.position_id in active_ids]
        breakdown = compute_manual_intervention_breakdown(
            scoped_actions, filters.date_from, filters.date_to
        )
        denominator = breakdown.intervention_positions_count

        def pct(count: int) -> Optional[float]:
            return (count / denominator) if denominator else None

        return ManualInterventionBreakdownDTO(
            reviewed_positions_count=breakdown.reviewed_positions_count,
            intervention_positions_count=breakdown.intervention_positions_count,
            items=[
                ManualInterventionCategoryDTO(
                    category="confirmed",
                    count=breakdown.confirmed_count,
                    percentage=pct(breakdown.confirmed_count),
                ),
                ManualInterventionCategoryDTO(
                    category="qty_corrected",
                    count=breakdown.qty_corrected_count,
                    percentage=pct(breakdown.qty_corrected_count),
                ),
                ManualInterventionCategoryDTO(
                    category="sku_corrected",
                    count=breakdown.sku_corrected_count,
                    percentage=pct(breakdown.sku_corrected_count),
                ),
                ManualInterventionCategoryDTO(
                    category="invalid",
                    count=None,
                    percentage=None,
                    available=False,
                    notes="Current persisted review model does not distinguish invalid from delete_position.",
                ),
                ManualInterventionCategoryDTO(
                    category="operator_marked_unknown",
                    count=breakdown.operator_marked_unknown_count,
                    percentage=pct(breakdown.operator_marked_unknown_count),
                    available=True,
                ),
                ManualInterventionCategoryDTO(
                    category="deleted",
                    count=breakdown.deleted_count,
                    percentage=pct(breakdown.deleted_count),
                ),
            ],
            notes=list(breakdown.notes),
        )
