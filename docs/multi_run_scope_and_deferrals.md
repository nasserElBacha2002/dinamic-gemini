# Multi-run scope and intentional deferrals (pre–next-phase)

This document records **known behavioral boundaries** after the multi-run rollout hardening pass. It complements `docs/multi_provider_planning_revision.md` and `docs/multi_provider_audit_final.md`.

## Analytics vs Aisle Results

- **Dashboard analytics** (`GET /api/v3/analytics/summary` and related aggregates) count **all non-deleted position rows** in the requested inventory/aisle scope unless a metric is explicitly job-scoped elsewhere.
- **Aisle Results** (positions list/detail) use **resolver semantics**: operational job, legacy-null slice, or an explicit `job_id` — a **single visible slice** per request.
- Therefore **dashboard totals must not be read as identical to** a single-run browse view. Summary responses include a **Multi-run** line in `notes`; the UI surfaces `notes` on the metrics page.

**Deferred:** Full alignment of analytics KPIs with per-aisle operational job exclusion (or per-run filters) is a larger product/analytics design task, not completed in this pass.

## Review queue

- Queue rows include `position.job_id` when the API provides it; the review drawer uses that value so opening from the queue targets the **same storage slice** as the row when `job_id` is present.
- Rows **without** `job_id` still follow resolver behavior on navigation to position detail (operational/legacy resolution on the server).

**Deferred:** A dedicated “browse queue per run” UX (e.g. filter queue by job) is not in scope here.

## Exports

- Unless documented otherwise on a specific export endpoint, exports remain **inventory- or scope-wide** as implemented; they are not automatically restricted to the same slice as Aisle Results.

## Process → results refresh

- Starting processing invalidates TanStack Query keys for the inventory, aisle jobs list, and positions for that aisle so the UI can pick up new runs without manual full reload.

See tests: `frontend/tests/useStartAisleProcessingRunContext.test.tsx`, analytics notes in `backend/tests/application/test_analytics_phase51.py`, and `frontend/tests/quickReviewContext.test.ts`.
