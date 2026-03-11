# Bug Investigation: GET /api/v1/inventory/jobs/{job_id}/entities returns 404

## Symptom

- **Request:** `GET /api/v1/inventory/jobs/79ea44b5-9609-4d83-8b41-2974c58d35c8/entities`
- **Response:** `404 Not Found`
- **Context:** The process/job was already generated (e.g. via v3 Process Aisle or legacy job creation), but fetching entities for that job returns 404.

## Expected Behavior

For a job that has completed successfully and produced a report, the entities endpoint should return the list of entities (and optional traceability summary) from the report.

## Area(s) Suspect

- **Platform:** API route registration, entities endpoint implementation, job/report resolution (`_resolve_report_and_run_dir`), and **v3 vs legacy job storage** (two separate job systems).

## Investigation Summary

### 1. Route registration

- **Route:** Declared in `src/api/routes/entities.py` as `@router.get("/{job_id}/entities")` on a router with `prefix="/api/v1/inventory/jobs"`.
- **Mount:** `src/api/server.py` includes `entities_router` with `app.include_router(entities_router)` (no extra prefix).
- **Full path:** `GET /api/v1/inventory/jobs/{job_id}/entities` — matches the client request.
- **Conclusion:** The route is registered and the path matches; this is **not** a route-level 404.

### 2. Endpoint implementation and 404 source

- **Handler:** `list_entities` in `src/api/routes/entities.py` (lines 57–107).
- It calls `_resolve_report_and_run_dir(job_id)` (from `src/api/routes/jobs`) then `_load_report(report_path)`.
- **All 404s** are raised inside `_resolve_report_and_run_dir` in `src/api/routes/jobs.py` (lines 349–393). The handler itself does not raise 404.
- **Conclusion:** The 404 is **resource-level**: the route is hit, but `_resolve_report_and_run_dir` raises 404 because the job or report cannot be resolved.

### 3. Data dependencies for the endpoint

The endpoint requires:

- A **job record** resolvable by the **legacy** path (legacy `jobs` DB table or FS `output/<job_id>/job.json`).
- That record must have **status** `succeeded`.
- That record must have **output.report_json_path** set.
- The **report file** at that path must exist (e.g. `hybrid_report.json`).

It does **not** require `traceability_summary` to exist in the report (that is optional; summary can be computed from entities). It reads from the **report file** (and optionally merged reviews in other endpoints), not from DB entities for the v1 response.

### 4. Job creation flow vs entities endpoint expectations

- **Legacy jobs** (video/photos upload via `POST /api/v1/inventory/jobs`):
  - Job ID format: `job_` + 16 hex chars (e.g. `job_79ea44b596094d83`).
  - Created via `create_job()` in `job_store` → `output/<job_id>/job.json` and optionally legacy `jobs` table.
  - Worker runs `run_job()` (no v3), writes `hybrid_report.json` to `output/<job_id>/run/`, then calls `update_job(..., output={report_json_path, ...})` and `_push_success_to_db`.
  - So legacy jobs have both FS `job.json` and (when DB enabled) legacy `jobs` row with `report_json_path` set.

- **V3 process_aisle jobs** (e.g. Process Aisle from v3 API):
  - Job ID format: **full UUID** (e.g. `79ea44b5-9609-4d83-8b41-2974c58d35c8`) from `V3JobQueueAdapter.enqueue()`.
  - Job is stored **only** in the **v3** system: `v3_jobs` table (or in-memory) via `JobRepository` (e.g. `SqlJobRepository`). No call to legacy `create_job()` or `update_job()`.
  - Worker runs `_try_v3_process_aisle()` first; on success, `V3JobExecutor` writes `hybrid_report.json` to `base_path / job_id / "run" / hybrid_report.json` and calls `_mark_success(job_id, aisle, report_path, now)`, which updates **only** the v3 `Job` entity (`result_json = {"report_path": str(report_path)}`). It does **not** write `output/<job_id>/job.json` and does **not** update the legacy `jobs` table.
  - So for v3 jobs: the **report file exists** on disk at the same path convention as legacy, but **no legacy job record** (no `job.json`, no legacy DB row) exists.

- **Mismatch:** `_resolve_report_and_run_dir` in `jobs.py` resolves the job **only** via:
  1. Legacy DB: `jobs_repo.get_job(job_id)` (legacy `jobs` table),
  2. Else FS: `get_job(base, job_id)` → `output/<job_id>/job.json`.

  For job_id `79ea44b5-9609-4d83-8b41-2974c58d35c8` (v3 UUID), the legacy table and FS have no record, so resolution fails with **404 "Job not found"** even though the v3 job exists and the report file exists.

### 5. Route-level vs resource-level 404

- **Case B — Resource-level 404:** The route exists and is matched. The handler calls `_resolve_report_and_run_dir(job_id)`, which tries only the legacy job store/DB. For a **v3** job, no legacy record exists, so it raises **HTTPException(404, "Job not found")** (around line 379 in `jobs.py`).

### 6. Epic 3.1 / recent changes

- The entities endpoint and traceability (3.1.B / 3.1.C) did not remove or mis-mount the route.
- The issue is **not** report shape or traceability_summary; it is that **v3 jobs are not visible to the legacy resolver** used by the v1 entities endpoint.

### 7. Most likely scenario for this exact request

- The job `79ea44b5-9609-4d83-8b41-2974c58d35c8` was created as a **v3 process_aisle** job (full UUID from v3 queue).
- The worker ran it via `V3JobExecutor`, wrote `hybrid_report.json` under `output/79ea44b5-9609-4d83-8b41-2974c58d35c8/run/`, and updated only the v3 job (e.g. `v3_jobs` row with `result_json.report_path`).
- No `job.json` was created under `output/79ea44b5-9609-4d83-8b41-2974c58d35c8/` and no row was written to the legacy `jobs` table.
- `GET .../entities` calls `_resolve_report_and_run_dir("79ea44b5-9609-4d83-8b41-2974c58d35c8")` → legacy DB returns None, `get_job(base, job_id)` returns None → **404 "Job not found"**.

---

## Investigation Verdict

- **Type:** **Resource/artifact missing from the resolver’s point of view** — more precisely, **job/report lookup mismatch**: the v1 entities endpoint resolves job and report only via the **legacy** job store/DB, while **v3 process_aisle jobs** exist only in the **v3** job store and never create a legacy record, so the resolver concludes “job not found”.

## Exact Failing Code Path

- **File:** `src/api/routes/jobs.py`
- **Function:** `_resolve_report_and_run_dir(job_id: str)`
- **Condition:** After trying legacy DB (when enabled) and then `get_job(base, job_id)` (FS), both fail to find a job for the given `job_id`. The code then raises `HTTPException(404, "Job not found")` at line 379 (FS fallback path) or 358 (legacy DB path when `job_data is None`).
- For a v3 UUID, the legacy DB path typically does not find the job (`job_data is None`), so 404 is raised at **358**; if DB is disabled or not used for this lookup, 404 is raised at **379**.

## Root Cause Analysis

- Two job systems coexist:
  - **Legacy:** `job_store` (FS `job.json`) + optional legacy `jobs` table; job_id like `job_<16hex>`; worker updates `job.json` and DB with `report_json_path`.
  - **V3:** `JobRepository` (v3_jobs table or memory); job_id = full UUID; `V3JobExecutor` updates only v3 job with `result_json.report_path`, does not create legacy job or set legacy `report_json_path`.
- The v1 entities endpoint (and other v1 endpoints that use `_resolve_report_and_run_dir`) rely **only** on the legacy resolver. So any job that exists **only** in v3 (e.g. process_aisle with UUID) is “not found” and returns 404 even when the report file exists on disk.

## Fix Recommendation

**Minimal fix:** In `_resolve_report_and_run_dir`, when the legacy path has not found a job (before raising 404 "Job not found"), try the **v3** job repository. If a v3 job exists with status `succeeded` and `result_json` contains `report_path`, resolve that path, ensure the file exists, and return `(report_path, report_path.parent)`. This keeps v1 entities working for v3 process_aisle jobs without duplicating job creation into the legacy store.

- **Concrete change:** In `src/api/routes/jobs.py`, inside `_resolve_report_and_run_dir`:
  1. After the legacy DB block and before/after the FS block, when we would raise `HTTPException(404, "Job not found")`, try v3: `get_job_repo().get_by_id(job_id)`.
  2. If v3 job exists, `status == JobStatus.SUCCEEDED`, and `result_json` has `report_path`, then `path = Path(result_json["report_path"])`; if `path.exists()`, return `(path, path.parent)`.
  3. Otherwise, raise the same 404 as today.

This requires a one-off import of `get_job_repo` from `src.runtime.v3_deps` and the v3 `JobStatus` (or string compare) so as not to tie the route to the domain enum if preferred.

## Optional Hardening

1. **Tests:** Add an integration/e2e test that creates a v3 process_aisle job (or mocks v3 job + report file), then calls `GET /api/v1/inventory/jobs/<v3_job_id>/entities` and asserts 200 and entity list (or at least not 404).
2. **Invariant / docs:** Document that v1 entities (and result/report/artifacts) support both legacy job IDs and v3 job IDs when the report file exists (and, for v3, when the v3 job is succeeded and has `report_path`).
3. **Monitoring:** Log when report resolution is satisfied via v3 fallback (e.g. debug log “Resolved report via v3 job”) to observe usage and troubleshoot.

## Debug Checklist (runbook)

1. Confirm the route: `GET /api/v1/inventory/jobs/{job_id}/entities` → 404.
2. Check job_id format: if it is a full UUID (e.g. `79ea44b5-9609-4d83-8b41-2974c58d35c8`), treat as likely v3 job.
3. Check legacy store: `output_dir / job_id / job.json` exists? Legacy DB row for `job_id`? If both missing → v3-only job.
4. Check v3 store: query `v3_jobs` (or in-memory repo) for `id = job_id`; if found and status = succeeded and `result_json.report_path` set, note path.
5. Check report file: `output_dir / job_id / run / hybrid_report.json` (or path from v3 `result_json.report_path`) exists?
6. If file exists but legacy job missing → apply fix: resolve report via v3 job when legacy lookup fails.
