"""
SQL Server analytics aggregates — Phase 5.1.

See `application/dto/analytics_dto.py` for metric definitions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
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
from src.application.services.analytics_aggregation_core import day_span_inclusive
from src.database.sqlserver import SqlServerClient


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _build_scope_sql(prefix: str = "p") -> Tuple[str, List[Any]]:
    """Returns (WHERE fragment without WHERE keyword, params). Base: active positions."""
    return f"{prefix}.status <> 'deleted'", []


def _append_inventory_aisle_filters(
    conditions: List[str],
    params: List[Any],
    filters: AnalyticsFilters,
) -> None:
    if filters.inventory_id:
        conditions.append("i.id = ?")
        params.append(filters.inventory_id.strip())
    if filters.aisle_id:
        conditions.append("a.id = ?")
        params.append(filters.aisle_id.strip())


def _append_ra_time_filters(
    conditions: List[str],
    params: List[Any],
    filters: AnalyticsFilters,
    col: str = "ra.created_at",
) -> None:
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


def _issue_bucket_expr(alias: str = "p") -> str:
    tr = _traceability_invalid_expr(alias)
    thr = float(LOW_CONFIDENCE_THRESHOLD)
    return f"""
    CASE
      WHEN {tr} THEN N'invalid_traceability'
      WHEN {alias}.primary_evidence_id IS NULL
        OR LTRIM(RTRIM(CAST({alias}.primary_evidence_id AS NVARCHAR(64)))) = N'' THEN N'missing_evidence'
      WHEN TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.final_quantity')) = 0
        OR TRY_CONVERT(int, JSON_VALUE({alias}.detected_summary_json, N'$.product_label_quantity')) = 0
        THEN N'quantity_zero'
      WHEN {alias}.confidence < CAST({thr} AS float) THEN N'low_confidence'
      WHEN {alias}.needs_review = 1 THEN N'pending_review'
      ELSE N'ok'
    END
    """


class SqlAnalyticsRepository(AnalyticsRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_summary(self, filters: AnalyticsFilters) -> AnalyticsSummaryDTO:
        notes: List[str] = []
        pos_where, pos_params = _build_scope_sql("p")
        conditions = [pos_where]
        params: List[Any] = list(pos_params)
        _append_inventory_aisle_filters(conditions, params, filters)
        # Position-state metrics: entity scope only (inventory/aisle), not position.updated_at.
        where_pos = " AND ".join(conditions)

        cond_ra = [
            "p.status <> 'deleted'",
            "ra.action_type IN (N'confirm', N'update_quantity', N'update_sku')",
        ]
        ra_params: List[Any] = []
        _append_inventory_aisle_filters(cond_ra, ra_params, filters)
        _append_ra_time_filters(cond_ra, ra_params, filters, "ra.created_at")
        where_ra = " AND ".join(cond_ra)

        tr_inv = _traceability_invalid_expr("p")
        sql_positions = f"""
            SELECT COUNT(*) AS cnt
            FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_pos}
        """
        sql_invalid = f"""
            SELECT SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_n
            FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_pos}
        """
        sql_reviews = f"""
            SELECT
              SUM(CASE WHEN ra.action_type IN (N'confirm', N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS settling,
              SUM(CASE WHEN ra.action_type = N'confirm' THEN 1 ELSE 0 END) AS confirms,
              SUM(CASE WHEN ra.action_type IN (N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS corrections
            FROM review_actions ra
            INNER JOIN positions p ON p.id = ra.position_id
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_ra}
        """
        sq_params = list(params)
        inv_params = list(params)
        rev_params = list(ra_params)
        lag_where_parts = [pos_where]
        lag_params: List[Any] = []
        _append_inventory_aisle_filters(lag_where_parts, lag_params, filters)
        _append_ra_time_filters(lag_where_parts, lag_params, filters, "r.first_ra")
        lag_where = " AND ".join(lag_where_parts)
        sql_avg_lag = f"""
            SELECT AVG(DATEDIFF_BIG(SECOND, p.created_at, r.first_ra)) AS avg_sec
            FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            INNER JOIN (
              SELECT position_id, MIN(created_at) AS first_ra
              FROM review_actions
              WHERE action_type IN (N'confirm', N'update_quantity', N'update_sku')
              GROUP BY position_id
            ) r ON r.position_id = p.id
            WHERE {lag_where}
              AND r.first_ra >= p.created_at
        """

        positions_in_scope = 0
        invalid_n = 0
        settling = confirms = corrections = 0
        avg_sec: Optional[float] = None
        with self._client.cursor() as cur:
            cur.execute(sql_positions, sq_params)
            row = cur.fetchone()
            positions_in_scope = int(getattr(row, "cnt", 0) or 0)

            cur.execute(sql_invalid, inv_params)
            row = cur.fetchone()
            invalid_n = int(getattr(row, "invalid_n", 0) or 0)

            cur.execute(sql_reviews, rev_params)
            row = cur.fetchone()
            settling = int(getattr(row, "settling", 0) or 0)
            confirms = int(getattr(row, "confirms", 0) or 0)
            corrections = int(getattr(row, "corrections", 0) or 0)

            cur.execute(sql_avg_lag, lag_params)
            row = cur.fetchone()
            raw_avg = getattr(row, "avg_sec", None)
            if raw_avg is not None:
                avg_sec = float(raw_avg)

        proc_success = self._processing_success_rate_sql(filters)

        auto_rate = (confirms / settling) if settling else None
        corr_rate = (corrections / settling) if settling else None
        inv_rate = (invalid_n / positions_in_scope) if positions_in_scope else None

        span = day_span_inclusive(filters.date_from, filters.date_to)
        rpd = (settling / span) if settling else None

        if filters.date_from is None or filters.date_to is None:
            notes.append(
                "Date range open-ended: settling_actions_per_day uses a 1-day divisor; "
                "set date_from and date_to for meaningful per-day rates."
            )

        return AnalyticsSummaryDTO(
            auto_acceptance_rate=auto_rate,
            manual_correction_rate=corr_rate,
            invalid_traceability_rate=inv_rate,
            processing_success_rate=proc_success,
            average_review_time_seconds=avg_sec,
            settling_actions_per_day=rpd,
            notes=notes,
            period_day_count=span,
            settling_actions_count=settling,
            positions_in_scope=positions_in_scope,
        )

    def _processing_success_rate_sql(self, filters: AnalyticsFilters) -> Optional[float]:
        conditions = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed')",
        ]
        params: List[Any] = []
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
        sql = f"""
            SELECT
              SUM(CASE WHEN j.status = N'succeeded' THEN 1 ELSE 0 END) AS ok_n,
              SUM(CASE WHEN j.status = N'failed' THEN 1 ELSE 0 END) AS fail_n
            FROM inventory_jobs j
            {join}
            WHERE {where_j}
        """
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

        cond_ra = ["p.status <> 'deleted'"]
        ra_params: List[Any] = []
        _append_inventory_aisle_filters(cond_ra, ra_params, filters)
        _append_ra_time_filters(cond_ra, ra_params, filters, "ra.created_at")
        where_ra = " AND ".join(cond_ra)

        sql_daily_reviews = f"""
            SELECT
              CONVERT(date, ra.created_at) AS d,
              SUM(CASE WHEN ra.action_type IN (N'confirm', N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS settling,
              SUM(CASE WHEN ra.action_type IN (N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS corrections
            FROM review_actions ra
            INNER JOIN positions p ON p.id = ra.position_id
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_ra}
            GROUP BY CONVERT(date, ra.created_at)
            ORDER BY d
        """

        cond_j = [
            "j.target_type = N'aisle'",
            "j.status IN (N'succeeded', N'failed')",
        ]
        j_params: List[Any] = []
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
        """

        reviewed_by_day: Dict[date, Tuple[int, int]] = {}
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

            jobs_by_day: Dict[date, Tuple[int, int]] = {}
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
        reviewed_series: List[TrendPointDTO] = []
        correction_series: List[TrendPointDTO] = []
        proc_series: List[TrendPointDTO] = []
        for dkey in all_days:
            s, c = reviewed_by_day.get(dkey, (0, 0))
            reviewed_series.append(TrendPointDTO(period=dkey.isoformat(), reviewed_results=s, correction_rate=None, processing_success_rate=None))
            cr = (c / s) if s else None
            correction_series.append(
                TrendPointDTO(period=dkey.isoformat(), reviewed_results=s, correction_rate=cr, processing_success_rate=None)
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

    def get_inventory_performance(self, filters: AnalyticsFilters) -> List[InventoryPerformanceRowDTO]:
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where]
        params: List[Any] = []
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
              SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_n
            FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_scope}
            GROUP BY i.id, i.name, i.created_at
            ORDER BY i.name ASC
        """
        rows_out: List[InventoryPerformanceRowDTO] = []
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                inv_id = str(getattr(row, "inventory_id", "") or "")
                total_pos = int(getattr(row, "total_positions", 0) or 0)
                rev = self._inventory_review_rates(inv_id, filters)
                proc = self._processing_success_rate_sql(
                    AnalyticsFilters(
                        date_from=filters.date_from,
                        date_to=filters.date_to,
                        inventory_id=inv_id,
                        aisle_id=None,
                    )
                )
                invalid_n = int(getattr(row, "invalid_n", 0) or 0)
                inv_tr_rate = (invalid_n / total_pos) if total_pos else None
                avg_c = getattr(row, "avg_confidence", None)
                rows_out.append(
                    InventoryPerformanceRowDTO(
                        inventory_id=inv_id,
                        inventory_name=str(getattr(row, "inventory_name", "") or ""),
                        inventory_created_at=_ensure_utc(getattr(row, "inventory_created_at", None))
                        or datetime.now(timezone.utc),
                        total_aisles=int(getattr(row, "total_aisles", 0) or 0),
                        total_positions=total_pos,
                        processed_positions=int(getattr(row, "processed_positions", 0) or 0),
                        review_rate=rev[0],
                        correction_rate=rev[1],
                        invalid_traceability_rate=inv_tr_rate,
                        avg_confidence=float(avg_c) if avg_c is not None else None,
                        processing_success_rate=proc,
                    )
                )
        return rows_out

    def _inventory_review_rates(
        self, inventory_id: str, filters: AnalyticsFilters
    ) -> Tuple[Optional[float], Optional[float]]:
        cond = [
            "p.status <> 'deleted'",
            "i.id = ?",
            "ra.action_type IN (N'confirm', N'update_quantity', N'update_sku')",
        ]
        prm: List[Any] = [inventory_id]
        _append_ra_time_filters(cond, prm, filters, "ra.created_at")
        where_ra = " AND ".join(cond)
        sql = f"""
            SELECT
              COUNT(DISTINCT ra.position_id) AS reviewed_positions,
              SUM(CASE WHEN ra.action_type IN (N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS corrections,
              SUM(CASE WHEN ra.action_type IN (N'confirm', N'update_quantity', N'update_sku') THEN 1 ELSE 0 END) AS settling
            FROM review_actions ra
            INNER JOIN positions p ON p.id = ra.position_id
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_ra}
        """
        cond_pos = ["p.status <> 'deleted'", "i.id = ?"]
        pm = [inventory_id]
        where_pos = " AND ".join(cond_pos)
        sql_total = f"""
            SELECT COUNT(*) AS cnt FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_pos}
        """
        with self._client.cursor() as cur:
            cur.execute(sql_total, pm)
            trow = cur.fetchone()
            total = int(getattr(trow, "cnt", 0) or 0)
            cur.execute(sql, prm)
            row = cur.fetchone()
        reviewed_pos = int(getattr(row, "reviewed_positions", 0) or 0)
        settling = int(getattr(row, "settling", 0) or 0)
        corrections = int(getattr(row, "corrections", 0) or 0)
        review_rate = (reviewed_pos / total) if total else None
        correction_rate = (corrections / settling) if settling else None
        return review_rate, correction_rate

    def get_aisle_issues(self, filters: AnalyticsFilters) -> List[AisleIssueRowDTO]:
        bucket = _issue_bucket_expr("p")
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where]
        params: List[Any] = []
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
              SUM(CASE WHEN {tr_inv} THEN 1 ELSE 0 END) AS invalid_traceability_count,
              SUM(CASE WHEN p.confidence < CAST({low_thr} AS float) THEN 1 ELSE 0 END) AS low_confidence_count,
              SUM(CASE WHEN ({bucket}) = N'invalid_traceability' THEN 1 ELSE 0 END) AS iss_invalid,
              SUM(CASE WHEN ({bucket}) = N'missing_evidence' THEN 1 ELSE 0 END) AS iss_missing,
              SUM(CASE WHEN ({bucket}) = N'quantity_zero' THEN 1 ELSE 0 END) AS iss_qty0,
              SUM(CASE WHEN ({bucket}) = N'low_confidence' THEN 1 ELSE 0 END) AS iss_lowc,
              SUM(CASE WHEN ({bucket}) = N'pending_review' THEN 1 ELSE 0 END) AS iss_pending
            FROM positions p
            INNER JOIN aisles a ON a.id = p.aisle_id
            INNER JOIN inventories i ON i.id = a.inventory_id
            WHERE {where_scope}
            GROUP BY a.id, a.code, i.id, i.name
            ORDER BY (SUM(CASE WHEN p.needs_review = 1 THEN 1 ELSE 0 END)) DESC, total_results DESC
        """
        labels = [
            ("iss_invalid", "Invalid traceability"),
            ("iss_missing", "Missing evidence"),
            ("iss_qty0", "Zero quantity"),
            ("iss_lowc", "Low confidence"),
            ("iss_pending", "Pending review"),
        ]
        out: List[AisleIssueRowDTO] = []
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
                        invalid_traceability_count=int(getattr(row, "invalid_traceability_count", 0) or 0),
                        low_confidence_count=int(getattr(row, "low_confidence_count", 0) or 0),
                        most_common_issue=best_label,
                    )
                )
        return out

    def get_quality_patterns(self, filters: AnalyticsFilters) -> List[QualityPatternRowDTO]:
        bucket_sql = _issue_bucket_expr("p")
        pos_where, _ = _build_scope_sql("p")
        conditions = [pos_where]
        params: List[Any] = []
        _append_inventory_aisle_filters(conditions, params, filters)
        where_scope = " AND ".join(conditions)
        sql = f"""
            SELECT bucket, COUNT(*) AS cnt
            FROM (
                SELECT {bucket_sql} AS bucket
                FROM positions p
                INNER JOIN aisles a ON a.id = p.aisle_id
                INNER JOIN inventories i ON i.id = a.inventory_id
                WHERE {where_scope}
            ) t
            GROUP BY bucket
        """
        display = {
            "invalid_traceability": "Invalid traceability",
            "missing_evidence": "Missing evidence",
            "quantity_zero": "Zero quantity in summary",
            "low_confidence": "Low confidence",
            "pending_review": "Pending review",
            "ok": "No primary issue",
        }
        thr_note = f"confidence < {LOW_CONFIDENCE_THRESHOLD} (LOW_CONFIDENCE_THRESHOLD)"
        notes = {
            "invalid_traceability": "traceability_status=invalid in detected summary",
            "missing_evidence": "No primary evidence id",
            "quantity_zero": "final_quantity or product_label_quantity is 0 in summary JSON",
            "low_confidence": thr_note,
            "pending_review": "needs_review flag set",
            "ok": "Did not match higher-priority buckets",
        }
        rows: List[Tuple[str, int]] = []
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                b = str(getattr(row, "bucket", "") or "").strip()
                c = int(getattr(row, "cnt", 0) or 0)
                rows.append((b, c))
        total = sum(c for _, c in rows) or 0
        out: List[QualityPatternRowDTO] = []
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
