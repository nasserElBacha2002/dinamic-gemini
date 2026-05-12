# H5 — Unified observability metrics backend + frontend

## 1. Executive summary

**Final status:** `READY_FOR_H6_FINAL_REVIEW_WITH_GAPS`

H5 delivers a bounded, read-only operational metrics slice: a single admin-protected backend endpoint aggregating job rows, aisle/inventory joins, optional H4 `run_audit_snapshot`, and `visual_reference_context` in `result_json` when no snapshot exists (for missing-reference heuristics only). The SPA exposes `/observabilidad` with Spanish copy, KPI cards, tables, filters, and explicit data-quality counters. No SQL migrations, no pipeline or prompt changes, and no scanning of `execution_log.jsonl` or `hybrid_report.json` by default.

**Gaps (intentional / documented):** no RBAC beyond existing admin gate, no rollup tables, capped job row scan (see backend service), partial metrics for legacy jobs without H4 snapshot, no exports, no heavy charting.

---

## 2. What was implemented

### Backend

- `GET /api/v3/observability/metrics` — admin-only, optional query filters.
- `ObservabilityMetricsService` — aggregation, rates, data-quality block.
- `JobRepository.list_jobs_for_metrics` — bounded, date-filtered job listing (SQL + in-memory implementations).
- Pydantic response schemas with JSON aliases (`range`, `from`).
- Focused service and API tests.

### Frontend

- API: `getObservabilityMetrics`, `getObservabilityMetricsPath`, types in `responses.ts`.
- Hook: `useObservabilityMetrics` (TanStack Query, 120s stale time).
- Page: `ObservabilityMetricsPage` at route `observabilidad`.
- Nav: primary item “Observabilidad”; shell top bar copy for the route.
- Spanish i18n under `observability.metrics.*`, `nav.observability`, `routes.observability_metrics.*`.
- Tests: API query string, hook loading path, page states.

### Documentation

- This file: `audit/phase-h/h5-unified-observability-metrics.md`.

---

## 3. Backend metrics contract

| Item | Detail |
|------|--------|
| **Method / path** | `GET /api/v3/observability/metrics` |
| **Auth** | Same as other internal v3 admin routes (`get_current_admin`). |
| **Query params** | `from`, `to` (optional datetimes), `client_id`, `client_supplier_id`, `provider_name`, `model_name` (optional strings). |
| **Default date range** | Last **30** days ending at `to` or “now” (UTC). |
| **Max date range** | **90** days; exceeding returns **422** with stable wire detail. |
| **Invalid range** | `from` after `to` → **422**. |
| **Response** | JSON object with `range`, `filters`, `totals`, `by_client`, `by_supplier`, `by_provider_model`, `data_quality` (snake_case). |
| **Partial data** | `data_quality.jobs_without_audit_snapshot` and UI helper explain incomplete secondary metrics for older jobs. |

---

## 4. Aggregation strategy

1. **Job rows** — identity, `status`, timestamps, `provider_name`, `model_name`, `target_type` / `target_id`, `result_json`.
2. **Joins** — aisle → `client_supplier_id`; inventory → `client_id` for `target_type == aisle`.
3. **H4 snapshot** — `result_json.run_audit_snapshot` with expected `schema_version`; enriches client/supplier when joins missing, drives `fallback_runs`, conservative missing-prompt counts, and supplier-reference missing-reference counts.
4. **`visual_reference_context`** — used only when **no** valid H4 snapshot, for conservative missing-reference signals (`resolved`, `resolution_error`).
5. **Artifacts** — execution logs and hybrid reports are **not** scanned (keeps latency predictable).
6. **Old jobs** — excluded from snapshot-derived signals where snapshot is absent; success/failure still from `JobStatus`; `legacy_runs` counts terminal jobs without a valid H4 snapshot.

---

## 5. Frontend integration

| Item | Detail |
|------|--------|
| **Route** | `/observabilidad` (`ROUTE_PATH.observabilidad`). |
| **Nav** | Label `nav.observability` (“Observabilidad”). |
| **Header** | `PageHeader` + shell top bar titles `routes.observability_metrics.*`. |
| **Filters** | Date from/to, optional client id, supplier id, provider, model; “Aplicar filtros”. |
| **KPIs** | Totals: runs, succeeded, failed, failure rate, fallbacks, missing prompt config, missing references, legacy. |
| **Tables** | By client, by supplier, by provider/model. |
| **Data quality** | Counts + Spanish helper for snapshot gaps. |
| **States** | Loading, error (with Spanish retry), empty, partial-data warning when `jobs_without_audit_snapshot > 0`. |

---

## 6. Metrics definitions

| Metric | Definition (implemented) |
|--------|---------------------------|
| `runs_total` | Count of **terminal** jobs in range after filters: succeeded, failed, or canceled. |
| `runs_succeeded` / `runs_failed` | Terminal jobs with `SUCCEEDED` vs `FAILED` or `CANCELED`. |
| `success_rate` / `failure_rate` | `runs_succeeded / runs_total`, `runs_failed / runs_total` (null if denominator 0). |
| `fallback_runs` | Succeeded jobs with H4 `supplier_prompt_fallback_used == true`. |
| `missing_prompt_config_runs` | Succeeded, client-resolved, H4 snapshot present: no `supplier_prompt_config_id` and (fallback used, specific fallback reason, or `prompt_composition_available`). |
| `missing_reference_runs` | Succeeded jobs: H4 supplier-reference rules **or** `visual_reference_context` unresolved / error when no snapshot. |
| `legacy_runs` | Terminal jobs **without** a valid H4 `run_audit_snapshot`. |
| `jobs_with_audit_snapshot` / `jobs_without_audit_snapshot` | Terminal jobs with vs without valid H4 snapshot. |
| `jobs_with_missing_metadata` | Heuristic: succeeded jobs missing snapshot or missing supplier prompt id when client is known. |
| `artifact_dependent_jobs` | Terminal jobs without valid H4 snapshot (same count as legacy in current implementation). |

---

## 7. i18n

**Added / used keys (Spanish only in UI):**

- `nav.observability`
- `routes.observability_metrics.title`, `routes.observability_metrics.subtitle`
- `observability.metrics.*` — title, subtitle, filters, KPI labels, table headers, loading/error/empty/partial notes, data quality strings.
- Retry button: `common.retry` (existing).

No new user-visible English strings were introduced for this page.

---

## 8. Tests and validation

Commands run during H5 implementation (2026-05-11):

**Backend**

```bash
cd backend && python3 -m pytest tests/application/services/test_observability_metrics_service.py tests/application/api/test_observability_metrics_endpoint.py -q
```

- Result: **7 passed, 1 skipped** (HTTP module skip on Python &lt; 3.10 where applicable).

```bash
cd backend && PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src
```

- Result: **success** (use `PYTHONDONTWRITEBYTECODE=1` if the environment cannot write `.pyc` under the system cache).

```bash
cd backend && python3 -m ruff check src/application/services/observability_metrics_service.py src/api/routes/v3/observability.py tests/application/services/test_observability_metrics_service.py tests/application/api/test_observability_metrics_endpoint.py
```

- Broader `ruff check src tests` surfaced a pre-existing **I001** in `tests/api/test_inventories_v3_wiring.py`; fixed with `ruff check … --fix` (import order only).

**Frontend**

```bash
cd frontend && npm run typecheck && npm run lint
cd frontend && npm test -- --run tests/observabilityMetricsApi.test.ts tests/useObservabilityMetrics.test.tsx tests/ObservabilityMetricsPage.test.tsx
cd frontend && npm run build
```

- Result: **typecheck and lint clean**, **8 tests passed**, **Vite build succeeded**.

---

## 9. Remaining gaps

- No SQL rollup tables or migrations.
- No default scanning of execution logs or hybrid reports.
- Metrics depend on a **bounded** job list (`METRICS_JOB_LIMIT`); very large tenants may hit the cap (logged).
- Old jobs without H4 snapshot: partial secondary metrics; failure/success still from status.
- No fine-grained RBAC beyond admin dependency.
- No CSV/export.
- No new chart library; tables + KPIs only.

---

## 10. Final recommendation

Proceed to **H6 — final Phase H review** with the above gaps documented as acceptable for an internal v1 metrics slice. Optional follow-ups (not blocking H6): **H5.1** permissions design if non-admin operators need read-only metrics; **H5.1** snapshot backfill for richer history; **H5.1** polish (client/supplier display names, trend charts) if product prioritizes them.
