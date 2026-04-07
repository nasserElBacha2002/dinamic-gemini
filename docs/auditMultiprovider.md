# Multi-provider / multi-run — audit note (historical filename)

**Canonical post-hardening reference:** [`multi_provider_audit_final.md`](./multi_provider_audit_final.md) and [`multi_provider_planning_revision.md`](./multi_provider_planning_revision.md).

This file formerly mixed **pre-fix** and **transitional** behavior descriptions. As of **2026-04**, the following applied to **Phases 1–5** (Phase 6 benchmark UX remains out of scope):

- **`ResultContextResolver`** is **strict:** explicit `job_id` → `operational_job_id` → **legacy** (`job_id IS NULL` on positions). There is **no** `latest_succeeded` (or any implicit newest-job) slice for **result reads**.
- **Merge / export / analytics (default)** follow the same **per-aisle operational vs legacy** rules; benchmark rows do not drive operational KPIs when the repository layer applies the shared predicate.
- **Evidence / HEIC previews** resolve paths via the **same context** as positions — **no** `get_latest_by_target` fallback for previews.
- **`prompt_version`** is stored on **`inventory_jobs` / domain `Job`**, derived as `{prompt_key}@v2.1` when the pipeline sets `prompt_key` but omits `prompt_version` in `run_metadata`. Position **detail** `run_context` exposes `prompt_version` with provider/model/prompt metadata.
- **Review mutations** are allowed only on the **operational slice** (server-enforced `403` outside that slice).
- **Frontend:** TanStack Query keys for aisle positions include an explicit **`job_slice`** (`resolver_default` vs `job_id`) so resolver-default lists do not alias explicit runs; review success invalidates **aisle-jobs** for the row as well as positions/merge/metrics.
- **Phase 4:** `GeminiSdkAdapter` / `OpenAiSdkAdapter` are **lazy-imported** inside `resolve_llm_executor` so `pipeline.providers.registry` does not eagerly import vendor SDK modules.

For remaining **Phase 6** work (compare UX, benchmark productization, correction transfer), see the planning revision — intentionally **not** implemented here.
