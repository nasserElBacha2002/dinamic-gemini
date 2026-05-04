"""
SQL Server analytics aggregates — Phase 5.1.

See `application/dto/analytics_dto.py` for metric definitions.

Position-based metrics use the same **per-aisle operational slice** as
:class:`~src.application.services.result_context_resolver.ResultContextResolver`:
``positions.job_id = aisles.operational_job_id`` when the pointer is set, else ``positions.job_id IS NULL``
(legacy). Non-operational runs for an aisle do not affect KPIs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
from src.application.dto.analytics_dto import (
    AisleIssueRowDTO,
    AnalyticsFilters,
    AnalyticsSummaryDTO,
    AnalyticsTrendsDTO,
    InventoryPerformanceRowDTO,
    ManualInterventionBreakdownDTO,
    ManualInterventionCategoryDTO,
    QualityPatternRowDTO,
    TrendPointDTO,
)
from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.services.analytics_aggregation_core import (
    InventoryMetricInputs,
    SummaryMetricInputs,
    build_inventory_metric_rates,
    build_summary_metrics,
    day_span_inclusive,
)
from src.database.sqlserver import SqlServerClient
from src.domain.reviews.sql_literals import (
    SQL_EQ_CONFIRM,
    SQL_EQ_DELETE_POSITION,
    SQL_EQ_MARK_IMAGE_MISMATCH,
    SQL_EQ_MARK_UNKNOWN,
    SQL_EQ_UPDATE_QUANTITY,
    SQL_EQ_UPDATE_SKU,
    SQL_IN_CORRECTION_ACTIONS,
    SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS,
    SQL_IN_REVIEWED_POSITIONS_ACTIONS,
    SQL_IN_SETTLING_ACTIONS,
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _build_scope_sql(prefix: str = "p") -> tuple[str, list[Any]]:
    """Returns (WHERE fragment without WHERE keyword, params). Base: active positions."""
    return f"{prefix}.status <> 'deleted'", []


def _operational_result_slice_predicate(p_alias: str = "p", a_alias: str = "a") -> str:
    """Match resolver semantics: operational job row per aisle, else legacy ``job_id IS NULL``."""
    return (
        f"((COALESCE({a_alias}.operational_job_id, N'') <> N'' AND {p_alias}.job_id = {a_alias}.operational_job_id) "
        f"OR (COALESCE({a_alias}.operational_job_id, N'') = N'' AND {p_alias}.job_id IS NULL))"
    )


def _unknown_resolution_expr(alias: str = "p") -> str:
    # Historical rows can remain NULL until touched by the Phase 4 review flow.
    # Unknown analytics count only explicit persisted unknown terminal resolutions.
    return f"{alias}.review_resolution = N'unknown'"


def _unidentified_product_expr(primary_alias: str = "pr_primary") -> str:
    return f"UPPER(LTRIM(RTRIM(ISNULL({primary_alias}.sku, N'')))) = N'UNKNOWN'"


def _append_inventory_aisle_filters(
    conditions: list[str],
    params: list[Any],
    filters: AnalyticsFilters,
) -> None:
    if filters.inventory_id:
        conditions.append("i.id = ?")
        params.append(filters.inventory_id.strip())
    if filters.aisle_id:
        conditions.append("a.id = ?")
        params.append(filters.aisle_id.strip())


def _append_ra_time_filters(
    conditions: list[str],
    params: list[Any],
    filters: AnalyticsFilters,
    col: str = "ra.created_at",
) -> None:
    if filters.date_from:
        conditions.append(f"{col} >= ?")
        params.append(_ensure_utc(filters.date_from))
    if filters.date_to:
        conditions.append(f"{col} <= ?")
        params.append(_ensure_utc(filters.date_to))


def _append_job_finished_at_time_filters(
    conditions: list[str],
    params: list[Any],
    filters: AnalyticsFilters,
    col: str = "j.finished_at",
) -> None:
    """Gate terminal job duration metrics by completion time (not review actions)."""
    if filters.date_from:
        conditions.append(f"{col} >= ?")
        params.append(_ensure_utc(filters.date_from))
    if filters.date_to:
        conditions.append(f"{col} <= ?")
        params.append(_ensure_utc(filters.date_to))


def _traceability_invalid_expr(alias: str = "p") -> str:
    return (
        f"LOWER(LTRIM(RTRIM(ISNULL(JSON_VALUE({alias}.detected_summary_json, "
        f"'$.traceability_status'), N'')))) = N'invalid'"
    )


def _aggregated_row_expr(alias: str = "p") -> str:
    return f"JSON_VALUE({alias}.detected_summary_json, N'$.aggregated_from_ids[0]') IS NOT NULL"


def _canonical_quantity_expr(alias: str = "p", primary_alias: str = "pr_primary") -> str:
    aggregated = _aggregated_row_expr(alias)
    return f"""
    CASE
      WHEN {aggregated} THEN
        COALESCE(
          TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.final_quantity')),
          TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.product_label_quantity')),
          0
        )
      WHEN {primary_alias}.id IS NOT NULL THEN
        COALESCE({primary_alias}.corrected_quantity, {primary_alias}.detected_quantity, 0)
      ELSE
        COALESCE(
          TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.final_quantity')),
          TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.product_label_quantity')),
          0
        )
    END
    """


def _issue_bucket_expr(alias: str = "p") -> str:
    tr = _traceability_invalid_expr(alias)
    unidentified = _unidentified_product_expr("pr_primary")
    thr = float(LOW_CONFIDENCE_THRESHOLD)
    qty_expr = _canonical_quantity_expr(alias, "pr_primary")
    return f"""
    CASE
      WHEN {unidentified} THEN N'unidentified_product'
      WHEN {tr} THEN N'invalid_traceability'
      WHEN {alias}.primary_evidence_id IS NULL
        OR LTRIM(RTRIM(CAST({alias}.primary_evidence_id AS NVARCHAR(64)))) = N'' THEN N'missing_evidence'
      WHEN ({qty_expr}) = 0 THEN N'quantity_zero'
      WHEN {alias}.confidence < CAST({thr} AS float) THEN N'low_confidence'
      WHEN {alias}.needs_review = 1 THEN N'pending_review'
      ELSE N'ok'
    END
    """


class SqlAnalyticsRepository(AnalyticsRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_summary(self, filters: AnalyticsFilters) -> AnalyticsSummaryDTO:
        notes: list[str] = []
        pos_where, pos_params = _build_scope_sql("p")
        conditions = [pos_where, _operational_result_slice_predicate()]
        params: list[Any] = list(pos_params)
        _append_inventory_aisle_filters(conditions, params, filters)
        # Position-state metrics: entity scope only (inventory/aisle), not position.updated_at.
        where_pos = " AND ".join(conditions)

        cond_ra = ["p.status <> 'deleted'", _operational_result_slice_predicate()]
        ra_params: list[Any] = []
        _append_inventory_aisle_filters(cond_ra, ra_params, filters)
        _append_ra_time_filters(cond_ra, ra_params, filters, "ra.created_at")
        where_ra = " AND ".join(cond_ra)

        tr_inv = _traceability_invalid_expr("p")
        processed_expr = (
            "CASE WHEN p.status IN (N'reviewed', N'corrected') OR "
            "(p.status = N'detected' AND p.needs_review = 0) THEN 1 ELSE 0 END"
        )
        # B608 FP-P: WHERE/skeleton built from internal fragments + constants (SQL_IN_*); bind params use "?".
        sql_positions = f"""
            SELECT
              COUNT(*) AS total_positions,
              SUM({processed_expr}) AS processed_positions,
              SUM(CASE WHEN {_unknown_resolution_expr("p")} THEN 1 ELSE 0 END) AS operator_marked_unknown_n,
              SUM(CASE WHEN {_unidentified_product_expr("pr_primary")} THEN 1 ELSE 0 END) AS unidentified_product_n,
              SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_n
            FROM positions p
            OUTER APPLY (
              SELECT TOP 1 pr.id, pr.sku
              FROM product_records pr
              WHERE pr.position_id = p.id
              ORDER BY pr.created_at ASC, pr.id ASC
            ) pr_primary
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_pos}
        """  # nosec B608
        sql_reviews = f"""
            SELECT
              COUNT(*) AS reviewed_positions,
              SUM(CASE WHEN t.latest_action_type IN ({SQL_IN_CORRECTION_ACTIONS}) THEN 1 ELSE 0 END) AS manually_corrected_positions,
              SUM(CASE WHEN t.latest_action_type = {SQL_EQ_CONFIRM} THEN 1 ELSE 0 END) AS auto_accepted_positions,
              SUM(CASE WHEN t.latest_action_type = {SQL_EQ_MARK_UNKNOWN} THEN 1 ELSE 0 END) AS unknown_positions,
              SUM(t.settling_actions) AS settling_actions
            FROM (
              SELECT
                ra.position_id AS position_id,
                MAX(CASE WHEN ra.rn = 1 THEN ra.action_type END) AS latest_action_type,
                SUM(CASE WHEN ra.action_type IN ({SQL_IN_SETTLING_ACTIONS}) THEN 1 ELSE 0 END) AS settling_actions
              FROM (
                SELECT
                  ra.position_id,
                  ra.action_type,
                  ra.created_at,
                  ra.id,
                  ROW_NUMBER() OVER (
                    PARTITION BY ra.position_id
                    ORDER BY ra.created_at DESC, ra.id DESC
                  ) AS rn
                FROM review_actions ra
                INNER JOIN positions p ON p.id = ra.position_id
                INNER JOIN aisles a ON a.id = p.aisle_id
                INNER JOIN inventories i ON i.id = a.inventory_id
                WHERE {where_ra}
                  AND ra.action_type IN ({SQL_IN_SETTLING_ACTIONS})
              ) ra
              GROUP BY ra.position_id
            ) t
        """  # nosec B608
        sq_params = list(params)
        list(params)
        rev_params = list(ra_params)
        job_proc_conditions = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed', N'canceled')",
            "j.started_at IS NOT NULL",
            "j.finished_at IS NOT NULL",
            "j.finished_at >= j.started_at",
        ]
        job_proc_params: list[Any] = []
        job_join = ""
        if filters.inventory_id or filters.aisle_id:
            job_join = (
                "INNER JOIN aisles a ON a.id = j.target_id "
                "INNER JOIN inventories i ON i.id = a.inventory_id"
            )
            _append_inventory_aisle_filters(job_proc_conditions, job_proc_params, filters)
        _append_job_finished_at_time_filters(job_proc_conditions, job_proc_params, filters)
        job_proc_where = " AND ".join(job_proc_conditions)
        # B608 DC: job_proc_where is AND of fixed predicates; only filter values are "?" (see _append_*).
        sql_avg_job_processing = f"""
            SELECT AVG(CAST(DATEDIFF_BIG(SECOND, j.started_at, j.finished_at) AS float)) AS avg_sec
            FROM inventory_jobs j
            {job_join}
            WHERE {job_proc_where}
        """  # nosec B608

        positions_in_scope = 0
        processed_positions_count = 0
        invalid_n = 0
        unidentified_product_n = 0
        reviewed_positions_count = 0
        auto_accepted_positions_count = 0
        manually_corrected_positions_count = 0
        unknown_positions_count = 0
        settling_actions_count = 0
        avg_sec: float | None = None
        with self._client.cursor() as cur:
            cur.execute(sql_positions, sq_params)
            row = cur.fetchone()
            positions_in_scope = int(getattr(row, "total_positions", 0) or 0)
            processed_positions_count = int(getattr(row, "processed_positions", 0) or 0)
            int(getattr(row, "operator_marked_unknown_n", 0) or 0)
            unidentified_product_n = int(getattr(row, "unidentified_product_n", 0) or 0)
            invalid_n = int(getattr(row, "invalid_n", 0) or 0)

            cur.execute(sql_reviews, rev_params)
            row = cur.fetchone()
            reviewed_positions_count = int(getattr(row, "reviewed_positions", 0) or 0)
            auto_accepted_positions_count = int(getattr(row, "auto_accepted_positions", 0) or 0)
            manually_corrected_positions_count = int(
                getattr(row, "manually_corrected_positions", 0) or 0
            )
            unknown_positions_count = int(getattr(row, "unknown_positions", 0) or 0)
            settling_actions_count = int(getattr(row, "settling_actions", 0) or 0)

            cur.execute(sql_avg_job_processing, job_proc_params)
            row = cur.fetchone()
            raw_avg = getattr(row, "avg_sec", None)
            if raw_avg is not None:
                avg_sec = float(raw_avg)

        proc_success = self._processing_success_rate_sql(filters)

        span = day_span_inclusive(filters.date_from, filters.date_to)
        rpd = (settling_actions_count / span) if settling_actions_count else None

        if filters.date_from is None or filters.date_to is None:
            notes.append(
                "Date range open-ended: settling_actions_per_day uses a 1-day divisor; "
                "set date_from and date_to for meaningful per-day rates."
            )
        notes.append(
            "Current-state metrics use entity scope; review-action date filters apply to review KPIs; "
            "average processing time and job success rate use job timestamps (finished_at / updated_at) in range."
        )
        return build_summary_metrics(
            SummaryMetricInputs(
                total_positions_in_scope=positions_in_scope,
                processed_positions_count=processed_positions_count,
                reviewed_positions_count=reviewed_positions_count,
                auto_accepted_positions_count=auto_accepted_positions_count,
                manually_corrected_positions_count=manually_corrected_positions_count,
                operator_marked_unknown_positions_count=unknown_positions_count,
                unidentified_product_positions_count=unidentified_product_n,
                invalid_traceability_positions_count=invalid_n,
                processing_success_rate=proc_success,
                average_processing_time_seconds=avg_sec,
                settling_actions_per_day=rpd,
                settling_actions_count=settling_actions_count,
                period_day_count=span,
                notes=notes,
            )
        )

    def _processing_success_rate_sql(self, filters: AnalyticsFilters) -> float | None:
        conditions = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed')",
        ]
        params: list[Any] = []
        if filters.date_from:
            conditions.append("j.updated_at >= ?")
            params.append(_ensure_utc(filters.date_from))
        if filters.date_to:
            conditions.append("j.updated_at <= ?")
            params.append(_ensure_utc(filters.date_to))
        join = ""
        if filters.inventory_id or filters.aisle_id:
            join = "INNER JOIN aisles a ON a.id = j.target_id INNER JOIN inventories i ON i.id = a.inventory_id"
            _append_inventory_aisle_filters(conditions, params, filters)
        where_j = " AND ".join(conditions)
        # B608 DC: where_j is internal predicates; dates/ids are always passed as "?" in params.
        sql = f"""
            SELECT
              SUM(CASE WHEN j.status = N'succeeded' THEN 1 ELSE 0 END) AS ok_n,
              SUM(CASE WHEN j.status = N'failed' THEN 1 ELSE 0 END) AS fail_n
            FROM inventory_jobs j
            {join}
            WHERE {where_j}
        """  # nosec B608
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        ok_n = int(getattr(row, "ok_n", 0) or 0)
        fail_n = int(getattr(row, "fail_n", 0) or 0)
        d = ok_n + fail_n
        if d == 0:
            return None
        return ok_n / d

    def get_trends(self, filters: AnalyticsFilters) -> AnalyticsTrendsDTO:
        if filters.date_from is None or filters.date_to is None:
            return AnalyticsTrendsDTO()

        cond_ra = ["p.status <> 'deleted'", _operational_result_slice_predicate()]
        ra_params: list[Any] = []
        _append_inventory_aisle_filters(cond_ra, ra_params, filters)
        _append_ra_time_filters(cond_ra, ra_params, filters, "ra.created_at")
        where_ra = " AND ".join(cond_ra)

        sql_daily_reviews = f"""
            SELECT
              CONVERT(date, ra.created_at) AS d,
              SUM(CASE WHEN ra.action_type IN ({SQL_IN_SETTLING_ACTIONS}) THEN 1 ELSE 0 END) AS settling,
              SUM(CASE WHEN ra.action_type = {SQL_EQ_MARK_UNKNOWN} THEN 1 ELSE 0 END) AS unknowns,
              SUM(CASE WHEN ra.action_type IN ({SQL_IN_CORRECTION_ACTIONS}) THEN 1 ELSE 0 END) AS corrections
            FROM review_actions ra
            INNER JOIN positions p ON p.id = ra.position_id
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_ra}
            GROUP BY CONVERT(date, ra.created_at)
            ORDER BY d
        """  # nosec B608

        cond_j = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed')",
        ]
        j_params: list[Any] = []
        if filters.date_from:
            cond_j.append("j.updated_at >= ?")
            j_params.append(_ensure_utc(filters.date_from))
        if filters.date_to:
            cond_j.append("j.updated_at <= ?")
            j_params.append(_ensure_utc(filters.date_to))
        join_j = ""
        if filters.inventory_id or filters.aisle_id:
            join_j = "INNER JOIN aisles a ON a.id = j.target_id INNER JOIN inventories i ON i.id = a.inventory_id"
            _append_inventory_aisle_filters(cond_j, j_params, filters)
        where_j = " AND ".join(cond_j)
        sql_daily_jobs = f"""
            SELECT
              CONVERT(date, j.updated_at) AS d,
              SUM(CASE WHEN j.status = N'succeeded' THEN 1 ELSE 0 END) AS ok_n,
              SUM(CASE WHEN j.status = N'failed' THEN 1 ELSE 0 END) AS fail_n
            FROM inventory_jobs j
            {join_j}
            WHERE {where_j}
            GROUP BY CONVERT(date, j.updated_at)
            ORDER BY d
        """  # nosec B608

        reviewed_by_day: dict[date, tuple[int, int]] = {}
        with self._client.cursor() as cur:
            cur.execute(sql_daily_reviews, ra_params)
            for row in cur.fetchall():
                d_raw = getattr(row, "d", None)
                if d_raw is None:
                    continue
                if isinstance(d_raw, datetime):
                    dkey = d_raw.date()
                else:
                    dkey = d_raw
                reviewed_by_day[dkey] = (
                    int(getattr(row, "settling", 0) or 0),
                    int(getattr(row, "corrections", 0) or 0),
                )

            jobs_by_day: dict[date, tuple[int, int]] = {}
            cur.execute(sql_daily_jobs, j_params)
            for row in cur.fetchall():
                d_raw = getattr(row, "d", None)
                if d_raw is None:
                    continue
                if isinstance(d_raw, datetime):
                    dkey = d_raw.date()
                else:
                    dkey = d_raw
                jobs_by_day[dkey] = (
                    int(getattr(row, "ok_n", 0) or 0),
                    int(getattr(row, "fail_n", 0) or 0),
                )

        all_days = sorted(set(reviewed_by_day.keys()) | set(jobs_by_day.keys()))
        reviewed_series: list[TrendPointDTO] = []
        correction_series: list[TrendPointDTO] = []
        proc_series: list[TrendPointDTO] = []
        for dkey in all_days:
            s, c = reviewed_by_day.get(dkey, (0, 0))
            reviewed_series.append(
                TrendPointDTO(
                    period=dkey.isoformat(),
                    reviewed_results=s,
                    correction_rate=None,
                    processing_success_rate=None,
                )
            )
            cr = (c / s) if s else None
            correction_series.append(
                TrendPointDTO(
                    period=dkey.isoformat(),
                    reviewed_results=s,
                    correction_rate=cr,
                    processing_success_rate=None,
                )
            )
            ok_n, fail_n = jobs_by_day.get(dkey, (0, 0))
            tot = ok_n + fail_n
            pr = (ok_n / tot) if tot else None
            proc_series.append(
                TrendPointDTO(
                    period=dkey.isoformat(),
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

    def get_inventory_performance(
        self, filters: AnalyticsFilters
    ) -> list[InventoryPerformanceRowDTO]:
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where, _operational_result_slice_predicate()]
        params: list[Any] = []
        _append_inventory_aisle_filters(conditions, params, filters)
        where_scope = " AND ".join(conditions)
        tr_inv = _traceability_invalid_expr("p")
        processed_expr = (
            "CASE WHEN p.status IN (N'reviewed', N'corrected') OR "
            "(p.status = N'detected' AND p.needs_review = 0) THEN 1 ELSE 0 END"
        )
        sql = f"""
            SELECT
              i.id AS inventory_id,
              i.name AS inventory_name,
              i.created_at AS inventory_created_at,
              COUNT(DISTINCT a.id) AS total_aisles,
              COUNT(*) AS total_positions,
              SUM({processed_expr}) AS processed_positions,
              AVG(CAST(p.confidence AS float)) AS avg_confidence,
              SUM(CASE WHEN {_unknown_resolution_expr("p")} THEN 1 ELSE 0 END) AS operator_marked_unknown_n,
              SUM(CASE WHEN {_unidentified_product_expr("pr_primary")} THEN 1 ELSE 0 END) AS unidentified_product_n,
              SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_n
            FROM positions p
            OUTER APPLY (
              SELECT TOP 1 pr.id, pr.sku
              FROM product_records pr
              WHERE pr.position_id = p.id
              ORDER BY pr.created_at ASC, pr.id ASC
            ) pr_primary
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_scope}
            GROUP BY i.id, i.name, i.created_at
            ORDER BY i.name ASC
        """  # nosec B608
        rows_out: list[InventoryPerformanceRowDTO] = []
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                inv_id = str(getattr(row, "inventory_id", "") or "")
                total_pos = int(getattr(row, "total_positions", 0) or 0)
                review_counts = self._inventory_review_outcomes(inv_id, filters)
                proc = self._processing_success_rate_sql(
                    AnalyticsFilters(
                        date_from=filters.date_from,
                        date_to=filters.date_to,
                        inventory_id=inv_id,
                        aisle_id=None,
                    )
                )
                invalid_n = int(getattr(row, "invalid_n", 0) or 0)
                avg_c = getattr(row, "avg_confidence", None)
                avg_proc_sec = self._inventory_average_processing_time_seconds(inv_id, filters)
                metric_rates = build_inventory_metric_rates(
                    InventoryMetricInputs(
                        total_positions_in_scope=total_pos,
                        processed_positions_count=int(getattr(row, "processed_positions", 0) or 0),
                        reviewed_positions_count=review_counts[0],
                        auto_accepted_positions_count=review_counts[1],
                        manually_corrected_positions_count=review_counts[2],
                        operator_marked_unknown_positions_count=review_counts[3],
                        unidentified_product_positions_count=int(
                            getattr(row, "unidentified_product_n", 0) or 0
                        ),
                        invalid_traceability_positions_count=invalid_n,
                        avg_confidence=float(avg_c) if avg_c is not None else None,
                        processing_success_rate=proc,
                        average_processing_time_seconds=avg_proc_sec,
                    )
                )
                rows_out.append(
                    InventoryPerformanceRowDTO(
                        inventory_id=inv_id,
                        inventory_name=str(getattr(row, "inventory_name", "") or ""),
                        inventory_created_at=_ensure_utc(getattr(row, "inventory_created_at", None))
                        or datetime.now(timezone.utc),
                        total_aisles=int(getattr(row, "total_aisles", 0) or 0),
                        aisles_count=int(getattr(row, "total_aisles", 0) or 0),
                        total_positions=total_pos,
                        positions_count=total_pos,
                        processed_positions=int(getattr(row, "processed_positions", 0) or 0),
                        processed_count=int(getattr(row, "processed_positions", 0) or 0),
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
                        average_processing_time_minutes=metric_rates[
                            "average_processing_time_minutes"
                        ],
                    )
                )
        return rows_out

    def _inventory_review_outcomes(
        self, inventory_id: str, filters: AnalyticsFilters
    ) -> tuple[int, int, int, int]:
        cond = [
            "p.status <> 'deleted'",
            _operational_result_slice_predicate(),
            "i.id = ?",
        ]
        prm: list[Any] = [inventory_id]
        _append_ra_time_filters(cond, prm, filters, "ra.created_at")
        where_ra = " AND ".join(cond)
        sql = f"""
            SELECT
              COUNT(*) AS reviewed_positions,
              SUM(CASE WHEN t.latest_action_type = {SQL_EQ_CONFIRM} THEN 1 ELSE 0 END) AS auto_accepted_positions,
              SUM(CASE WHEN t.latest_action_type IN ({SQL_IN_CORRECTION_ACTIONS}) THEN 1 ELSE 0 END) AS manually_corrected_positions,
              SUM(CASE WHEN t.latest_action_type = {SQL_EQ_MARK_UNKNOWN} THEN 1 ELSE 0 END) AS unknown_positions
            FROM (
              SELECT
                ra.position_id AS position_id,
                MAX(CASE WHEN ra.rn = 1 THEN ra.action_type END) AS latest_action_type
              FROM (
                SELECT
                  ra.position_id,
                  ra.action_type,
                  ROW_NUMBER() OVER (
                    PARTITION BY ra.position_id
                    ORDER BY ra.created_at DESC, ra.id DESC
                  ) AS rn
                FROM review_actions ra
                INNER JOIN positions p ON p.id = ra.position_id
                INNER JOIN aisles a ON a.id = p.aisle_id
                INNER JOIN inventories i ON i.id = a.inventory_id
                WHERE {where_ra}
                  AND ra.action_type IN ({SQL_IN_SETTLING_ACTIONS})
              ) ra
              GROUP BY ra.position_id
            ) t
        """  # nosec B608
        with self._client.cursor() as cur:
            cur.execute(sql, prm)
            row = cur.fetchone()
        reviewed_pos = int(getattr(row, "reviewed_positions", 0) or 0)
        auto_accepted = int(getattr(row, "auto_accepted_positions", 0) or 0)
        manually_corrected = int(getattr(row, "manually_corrected_positions", 0) or 0)
        unknown_positions = int(getattr(row, "unknown_positions", 0) or 0)
        return reviewed_pos, auto_accepted, manually_corrected, unknown_positions

    def _inventory_average_processing_time_seconds(
        self, inventory_id: str, filters: AnalyticsFilters
    ) -> float | None:
        cond = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed', N'canceled')",
            "j.started_at IS NOT NULL",
            "j.finished_at IS NOT NULL",
            "j.finished_at >= j.started_at",
            "i.id = ?",
        ]
        params: list[Any] = [inventory_id]
        if filters.aisle_id:
            cond.append("a.id = ?")
            params.append(filters.aisle_id.strip())
        _append_job_finished_at_time_filters(cond, params, filters)
        where_sql = " AND ".join(cond)
        sql = f"""
            SELECT AVG(CAST(DATEDIFF_BIG(SECOND, j.started_at, j.finished_at) AS float)) AS avg_sec
            FROM inventory_jobs j
            INNER JOIN aisles a ON a.id = j.target_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_sql}
        """  # nosec B608
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        raw_avg = getattr(row, "avg_sec", None)
        if raw_avg is None:
            return None
        return float(raw_avg)

    def get_aisle_issues(self, filters: AnalyticsFilters) -> list[AisleIssueRowDTO]:
        bucket = _issue_bucket_expr("p")
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where, _operational_result_slice_predicate()]
        params: list[Any] = []
        _append_inventory_aisle_filters(conditions, params, filters)
        where_scope = " AND ".join(conditions)
        tr_inv = _traceability_invalid_expr("p")
        low_thr = float(LOW_CONFIDENCE_THRESHOLD)
        sql = f"""
            SELECT
              a.id AS aisle_id,
              a.code AS aisle_code,
              i.id AS inventory_id,
              i.name AS inventory_name,
              COUNT(*) AS total_results,
              SUM(CASE WHEN p.needs_review = 1 THEN 1 ELSE 0 END) AS needs_review_count,
              SUM(CASE WHEN p.status = N'corrected' THEN 1 ELSE 0 END) AS corrected_count,
              SUM(CASE WHEN {_unknown_resolution_expr("p")} THEN 1 ELSE 0 END) AS operator_marked_unknown_count,
              SUM(CASE WHEN {_unidentified_product_expr("pr_primary")} THEN 1 ELSE 0 END) AS unidentified_product_count,
              SUM(CASE WHEN p.review_resolution IN (N'qty_corrected', N'sku_corrected') THEN 1 ELSE 0 END) AS manual_corrections_count,
              SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_traceability_count,
              SUM(CASE WHEN p.confidence < CAST({low_thr} AS float) THEN 1 ELSE 0 END) AS low_confidence_count,
              SUM(CASE WHEN ({bucket}) = N'unidentified_product' THEN 1 ELSE 0 END) AS iss_unidentified_product,
              SUM(CASE WHEN ({bucket}) = N'invalid_traceability' THEN 1 ELSE 0 END) AS iss_invalid,
              SUM(CASE WHEN ({bucket}) = N'missing_evidence' THEN 1 ELSE 0 END) AS iss_missing,
              SUM(CASE WHEN ({bucket}) = N'quantity_zero' THEN 1 ELSE 0 END) AS iss_qty0,
              SUM(CASE WHEN ({bucket}) = N'low_confidence' THEN 1 ELSE 0 END) AS iss_lowc,
              SUM(CASE WHEN ({bucket}) = N'pending_review' THEN 1 ELSE 0 END) AS iss_pending
            FROM positions p
            OUTER APPLY (
              SELECT TOP 1 pr.id, pr.sku, pr.detected_quantity, pr.corrected_quantity
              FROM product_records pr
              WHERE pr.position_id = p.id
              ORDER BY pr.created_at ASC, pr.id ASC
            ) pr_primary
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_scope}
            GROUP BY a.id, a.code, i.id, i.name
            ORDER BY (SUM(CASE WHEN p.needs_review = 1 THEN 1 ELSE 0 END)) DESC, total_results DESC
        """  # nosec B608
        labels = [
            ("iss_unidentified_product", "Unidentified product"),
            ("iss_invalid", "Invalid traceability"),
            ("iss_missing", "Missing evidence"),
            ("iss_qty0", "Zero quantity"),
            ("iss_lowc", "Low confidence"),
            ("iss_pending", "Pending review"),
        ]
        out: list[AisleIssueRowDTO] = []
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                counts = {k: int(getattr(row, k, 0) or 0) for k, _ in labels}
                best_label = None
                best_n = -1
                for key, lab in labels:
                    n = counts.get(key, 0)
                    if n > best_n:
                        best_n = n
                        best_label = lab
                if best_n <= 0:
                    best_label = None
                out.append(
                    AisleIssueRowDTO(
                        aisle_id=str(getattr(row, "aisle_id", "") or ""),
                        aisle_code=str(getattr(row, "aisle_code", "") or ""),
                        inventory_id=str(getattr(row, "inventory_id", "") or ""),
                        inventory_name=str(getattr(row, "inventory_name", "") or ""),
                        total_results=int(getattr(row, "total_results", 0) or 0),
                        needs_review_count=int(getattr(row, "needs_review_count", 0) or 0),
                        corrected_count=int(getattr(row, "corrected_count", 0) or 0),
                        operator_marked_unknown_count=int(
                            getattr(row, "operator_marked_unknown_count", 0) or 0
                        ),
                        unidentified_product_count=int(
                            getattr(row, "unidentified_product_count", 0) or 0
                        ),
                        unknown_count=int(getattr(row, "operator_marked_unknown_count", 0) or 0),
                        manual_corrections_count=int(
                            getattr(row, "manual_corrections_count", 0) or 0
                        ),
                        invalid_traceability_count=int(
                            getattr(row, "invalid_traceability_count", 0) or 0
                        ),
                        low_confidence_count=int(getattr(row, "low_confidence_count", 0) or 0),
                        most_common_issue=best_label,
                    )
                )
        return out

    def get_quality_patterns(self, filters: AnalyticsFilters) -> list[QualityPatternRowDTO]:
        bucket_sql = _issue_bucket_expr("p")
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where, _operational_result_slice_predicate()]
        params: list[Any] = []
        _append_inventory_aisle_filters(conditions, params, filters)
        where_scope = " AND ".join(conditions)
        sql = f"""
            SELECT bucket, COUNT(*) AS cnt
            FROM (
                SELECT {bucket_sql} AS bucket
                FROM positions p
                OUTER APPLY (
                  SELECT TOP 1 pr.id, pr.sku, pr.detected_quantity, pr.corrected_quantity
                  FROM product_records pr
                  WHERE pr.position_id = p.id
                  ORDER BY pr.created_at ASC, pr.id ASC
                ) pr_primary
                INNER JOIN aisles a ON a.id = p.aisle_id
                INNER JOIN inventories i ON i.id = a.inventory_id
                WHERE {where_scope}
            ) t
            GROUP BY bucket
        """  # nosec B608
        display = {
            "unidentified_product": "Unidentified product",
            "invalid_traceability": "Invalid traceability",
            "missing_evidence": "Missing evidence",
            "quantity_zero": "Zero quantity in summary",
            "low_confidence": "Low confidence",
            "pending_review": "Pending review",
            "ok": "No primary issue",
        }
        thr_note = f"confidence < {LOW_CONFIDENCE_THRESHOLD} (LOW_CONFIDENCE_THRESHOLD)"
        notes = {
            "unidentified_product": "Display-primary product SKU is persisted as UNKNOWN",
            "invalid_traceability": "traceability_status=invalid in canonical traceability source",
            "missing_evidence": "No primary evidence id",
            "quantity_zero": "Canonical final quantity resolved as 0 (product record when available; aggregated rows may fall back to snapshot)",
            "low_confidence": thr_note,
            "pending_review": "needs_review flag set",
            "ok": "Did not match higher-priority buckets",
        }
        rows: list[tuple[str, int]] = []
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                b = str(getattr(row, "bucket", "") or "").strip()
                c = int(getattr(row, "cnt", 0) or 0)
                rows.append((b, c))
        total = sum(c for _, c in rows) or 0
        out: list[QualityPatternRowDTO] = []
        for b, c in sorted(rows, key=lambda x: -x[1]):
            pct = (c / total) if total else None
            key = b.lower() if b else "ok"
            out.append(
                QualityPatternRowDTO(
                    issue_type=display.get(key, b),
                    count=c,
                    percentage=pct,
                    notes=notes.get(key),
                )
            )
        return out

    def get_manual_intervention_breakdown(
        self, filters: AnalyticsFilters
    ) -> ManualInterventionBreakdownDTO:
        cond = ["p.status <> 'deleted'", _operational_result_slice_predicate()]
        params: list[Any] = []
        _append_inventory_aisle_filters(cond, params, filters)
        _append_ra_time_filters(cond, params, filters, "ra.created_at")
        where_sql = " AND ".join(cond)
        sql = f"""
            WITH scoped_actions AS (
              SELECT
                ra.position_id,
                ra.action_type,
                ra.created_at,
                ra.id,
                ROW_NUMBER() OVER (
                  PARTITION BY ra.position_id
                  ORDER BY ra.created_at DESC, ra.id DESC
                ) AS rn
              FROM review_actions ra
              INNER JOIN positions p ON p.id = ra.position_id
              INNER JOIN aisles a ON a.id = p.aisle_id
              INNER JOIN inventories i ON i.id = a.inventory_id
              WHERE {where_sql}
                AND ra.action_type IN ({SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS})
            )
            SELECT
              SUM(CASE WHEN rn = 1 THEN 1 ELSE 0 END) AS intervention_positions_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_CONFIRM} THEN 1 ELSE 0 END) AS confirmed_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_UPDATE_QUANTITY} THEN 1 ELSE 0 END) AS qty_corrected_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_UPDATE_SKU} THEN 1 ELSE 0 END) AS sku_corrected_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_MARK_UNKNOWN} THEN 1 ELSE 0 END) AS unknown_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_MARK_IMAGE_MISMATCH} THEN 1 ELSE 0 END) AS image_mismatch_count,
              SUM(CASE WHEN rn = 1 AND action_type = {SQL_EQ_DELETE_POSITION} THEN 1 ELSE 0 END) AS deleted_count,
              COUNT(DISTINCT CASE WHEN action_type IN ({SQL_IN_REVIEWED_POSITIONS_ACTIONS}) THEN position_id END) AS reviewed_positions_count
            FROM scoped_actions
        """  # nosec B608
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()

        intervention_positions_count = int(getattr(row, "intervention_positions_count", 0) or 0)

        def pct(count: int) -> float | None:
            return (count / intervention_positions_count) if intervention_positions_count else None

        confirmed_count = int(getattr(row, "confirmed_count", 0) or 0)
        qty_corrected_count = int(getattr(row, "qty_corrected_count", 0) or 0)
        sku_corrected_count = int(getattr(row, "sku_corrected_count", 0) or 0)
        operator_marked_unknown_count = int(getattr(row, "unknown_count", 0) or 0)
        image_mismatch_count = int(getattr(row, "image_mismatch_count", 0) or 0)
        deleted_count = int(getattr(row, "deleted_count", 0) or 0)

        return ManualInterventionBreakdownDTO(
            reviewed_positions_count=int(getattr(row, "reviewed_positions_count", 0) or 0),
            intervention_positions_count=intervention_positions_count,
            items=[
                ManualInterventionCategoryDTO(
                    category="confirmed",
                    count=confirmed_count,
                    percentage=pct(confirmed_count),
                ),
                ManualInterventionCategoryDTO(
                    category="qty_corrected",
                    count=qty_corrected_count,
                    percentage=pct(qty_corrected_count),
                ),
                ManualInterventionCategoryDTO(
                    category="sku_corrected",
                    count=sku_corrected_count,
                    percentage=pct(sku_corrected_count),
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
                    count=operator_marked_unknown_count,
                    percentage=pct(operator_marked_unknown_count),
                    available=True,
                ),
                ManualInterventionCategoryDTO(
                    category="image_mismatch",
                    count=image_mismatch_count,
                    percentage=pct(image_mismatch_count),
                    available=True,
                    notes="Wrong image/evidence association flagged; SKU/qty unchanged",
                ),
                ManualInterventionCategoryDTO(
                    category="deleted",
                    count=deleted_count,
                    percentage=pct(deleted_count),
                ),
            ],
            notes=[
                "invalid category unavailable: current persisted review model does not distinguish invalid from delete_position",
            ],
        )
