# Phase 6 — Benchmark product layer (multi-run UX)

Phase 6 adds **benchmark-oriented** workflows on top of the Phase 1–5 multi-run foundation. It does **not**
change `ResultContextResolver` rules, persistence shape, or default operational/export/analytics slices.

## Principles

- **Operational defaults unchanged:** inventory export, operational KPIs / analytics queries, and resolver-driven
  reads behave as before unless the user explicitly uses benchmark endpoints or UI.
- **No implicit latest-run reads:** compare and benchmark export require **explicit** `job_id` values.
- **Same aisle only:** compare and benchmark export validate both jobs belong to the requested aisle and inventory.
- **Correction transfer:** promoting a run does **not** copy review corrections from other runs (unless a future
  phase implements that explicitly).

## Backend

### Compare (benchmark analytics payload)

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare?job_a_id=&job_b_id=`
  - Read-only JSON: per-run metrics (consolidated counts, totals, unknown internal-code count, needs-review),
    diff summary, and capped diff rows (SKU / position-code / quantity alignment uses consolidation keys).
- **Mirror (admin analytics namespace):**
  `GET /api/v3/analytics/benchmark/inventories/{inventory_id}/aisles/{aisle_id}/compare?job_a_id=&job_b_id=`
  - Same body as the inventory-scoped route; kept separate from operational `/analytics/summary` KPIs.

### Promotion

- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/promote-operational` with `{ "job_id": "..." }`
  - Only **succeeded** `process_aisle` jobs for that aisle; updates `aisles.operational_job_id`.
  - Benchmark rows remain persisted; review mutability follows the new operational pointer.

### Benchmark export (explicit only)

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export?format=csv`
  - **Exactly one** mode:
    - `run_job_id=` — operational-shaped CSV rows for that job slice **plus** benchmark metadata columns, or
    - `job_a_id=` **and** `job_b_id=` — compare diff rows CSV.
  - Default operational inventory export: unchanged (`GET /api/v3/inventories/{id}/export`).

### Jobs list enrichment

- `GET .../aisles/{aisle_id}/jobs` — each `JobSummary` includes `is_operational` when it matches
  `operational_job_id`.

## Frontend

- **Run selector:** operational vs benchmark chips, provider / model / prompt / `prompt_version`, scrollable menu,
  corrected resolver caption (no “latest succeeded” fallback).
- **Compare page:** `/inventories/:inventoryId/aisles/:aisleId/compare?jobAId=&jobBId=` — read-only metrics,
  diff tables, benchmark CSV export.
- **Aisle results:** “Compare runs…”, “Compare to operational” shortcut, “Promote run to operational…” with
  confirmation; merge disabled when viewing a non-operational (benchmark) slice.

## Tests

- Use-case tests: `test_compare_aisle_runs.py`, `test_promote_aisle_operational_job.py`.
- API tests (Python ≥ 3.10 recommended for Pydantic v2 auth schemas): `test_phase6_benchmark_api.py`.
