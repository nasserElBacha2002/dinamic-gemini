"""
In-memory analytics — aggregates from v3 repositories (no SQL).

Processing success rate is omitted unless ``extra_jobs`` is provided (tests).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Dict, List, Optional, Sequence

from src.application.dto.analytics_dto import (
    AnalyticsFilters,
    AnalyticsSummaryDTO,
    AnalyticsTrendsDTO,
    AisleIssueRowDTO,
    InventoryPerformanceRowDTO,
    QualityPatternRowDTO,
    TrendPointDTO,
)
from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ReviewActionRepository,
)
from src.application.services.analytics_aggregation_core import (
    aggregate_settling_metrics,
    compute_average_review_time_seconds,
    compute_processing_success_rate,
    correction_action,
    day_span_inclusive,
    issue_bucket_for_position,
    most_common_issue_for_counts,
    position_in_scope,
    settling_action,
    active_position,
    is_invalid_traceability,
    review_action_in_period,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus


class MemoryAnalyticsRepository(AnalyticsRepository):
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        review_action_repo: ReviewActionRepository,
        extra_jobs: Optional[Sequence[Job]] = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._review_action_repo = review_action_repo
        self._extra_jobs = list(extra_jobs) if extra_jobs is not None else None

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
        settling, confirms, corrections = aggregate_settling_metrics(
            actions,
            filters.date_from,
            filters.date_to,
        )
        invalid_n = sum(1 for p in active.values() if is_invalid_traceability(p))
        pos_den = len(active)
        auto_rate = (confirms / settling) if settling else None
        corr_rate = (corrections / settling) if settling else None
        inv_rate = (invalid_n / pos_den) if pos_den else None

        allowed_aisles = set(aisle_to_inv.keys())
        if filters.aisle_id:
            allowed_aisles &= {filters.aisle_id}
        jobs_list = self._extra_jobs or []
        proc = (
            compute_processing_success_rate(jobs_list, filters.date_from, filters.date_to, allowed_aisles)
            if jobs_list
            else None
        )
        if not jobs_list:
            notes.append("Processing success rate unavailable in in-memory mode without injected jobs.")

        avg_sec = compute_average_review_time_seconds(positions, actions, filters.date_from, filters.date_to)
        span = day_span_inclusive(filters.date_from, filters.date_to)
        rpd = (settling / span) if settling else None
        if filters.date_from is None or filters.date_to is None:
            notes.append(
                "Date range open-ended: reviewed_results_per_day uses a 1-day divisor; "
                "set date_from and date_to for meaningful per-day rates."
            )
        return AnalyticsSummaryDTO(
            auto_acceptance_rate=auto_rate,
            manual_correction_rate=corr_rate,
            invalid_traceability_rate=inv_rate,
            processing_success_rate=proc,
            average_review_time_seconds=avg_sec,
            reviewed_results_per_day=rpd,
            notes=notes,
            period_day_count=span,
            settling_actions_count=settling,
            positions_in_scope=pos_den,
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
            s = len(day_actions)
            c = sum(1 for a in day_actions if correction_action(a))
            reviewed_series.append(
                TrendPointDTO(period=d, reviewed_results=s, correction_rate=None, processing_success_rate=None)
            )
            correction_series.append(
                TrendPointDTO(period=d, reviewed_results=s, correction_rate=(c / s) if s else None, processing_success_rate=None)
            )

        proc_series: List[TrendPointDTO] = []
        jobs_list = self._extra_jobs or []
        if jobs_list:
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
            aisles = self._aisle_repo.list_by_inventory(inv.id)
            if filters.aisle_id:
                aisles = [a for a in aisles if a.id == filters.aisle_id]
            total_aisles = len(aisles)
            total_pos = len(active_list)
            if total_aisles == 0 and total_pos == 0:
                continue
            processed_n = sum(
                1
                for p in active_list
                if p.status in (PositionStatus.REVIEWED, PositionStatus.CORRECTED)
                or (p.status == PositionStatus.DETECTED and not p.needs_review)
            )
            invalid_n = sum(1 for p in active_list if is_invalid_traceability(p))
            conf_vals = [p.confidence for p in active_list]
            avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else None

            settling, _, corrections = aggregate_settling_metrics(actions, filters.date_from, filters.date_to)
            reviewed_positions = {
                ra.position_id
                for ra in actions
                if review_action_in_period(ra, filters.date_from, filters.date_to) and settling_action(ra)
                and ra.position_id in positions
            }
            review_rate = (len(reviewed_positions) / total_pos) if total_pos else None
            correction_rate = (corrections / settling) if settling else None
            inv_tr_rate = (invalid_n / total_pos) if total_pos else None

            aisle_ids = {a.id for a in aisles}
            jobs_list = self._extra_jobs or []
            proc = compute_processing_success_rate(
                jobs_list, filters.date_from, filters.date_to, aisle_ids if jobs_list else None
            )

            created = inv.created_at if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=timezone.utc)
            out.append(
                InventoryPerformanceRowDTO(
                    inventory_id=inv.id,
                    inventory_name=inv.name,
                    inventory_created_at=created,
                    total_aisles=total_aisles,
                    total_positions=total_pos,
                    processed_positions=processed_n,
                    review_rate=review_rate,
                    correction_rate=correction_rate,
                    invalid_traceability_rate=inv_tr_rate,
                    avg_confidence=avg_conf,
                    processing_success_rate=proc,
                )
            )
        return sorted(out, key=lambda r: r.inventory_name.lower())

    def get_aisle_issues(self, filters: AnalyticsFilters) -> List[AisleIssueRowDTO]:
        rows: List[AisleIssueRowDTO] = []
        positions, _, pos_to_aisle, _ = self._collect(filters)
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
            invalid_tr = sum(1 for p in plist if is_invalid_traceability(p))
            low_conf = sum(1 for p in plist if p.confidence < 0.5)
            bucket_counts: Dict[str, int] = {}
            for p in plist:
                b = issue_bucket_for_position(p)
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
                    invalid_traceability_count=invalid_tr,
                    low_confidence_count=low_conf,
                    most_common_issue=common,
                )
            )
        return sorted(rows, key=lambda r: (-r.needs_review_count, -r.total_results))

    def get_quality_patterns(self, filters: AnalyticsFilters) -> List[QualityPatternRowDTO]:
        positions, _, _, _ = self._collect(filters)
        counts: Dict[str, int] = {}
        for p in positions.values():
            if not active_position(p):
                continue
            b = issue_bucket_for_position(p)
            counts[b] = counts.get(b, 0) + 1
        total = sum(counts.values()) or 0
        display = {
            "invalid_traceability": "Invalid traceability",
            "missing_evidence": "Missing evidence",
            "quantity_zero": "Zero quantity in summary",
            "low_confidence": "Low confidence",
            "pending_review": "Pending review",
            "ok": "No primary issue",
        }
        notes_map = {
            "invalid_traceability": "traceability_status=invalid in detected summary",
            "missing_evidence": "No primary evidence id",
            "quantity_zero": "final_quantity or product_label_quantity is 0 in summary JSON",
            "low_confidence": "confidence < 0.5 (operational threshold)",
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
