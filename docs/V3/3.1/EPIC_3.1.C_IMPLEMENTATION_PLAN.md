# Epic 3.1.C — Backend Implementation Plan (review/audit traceability)

**Scope:** Backend-only. Richer traceability-oriented reporting, export, review summaries, and diagnostic policy. No frontend. No multi-evidence.

**Source of truth:** `docs/V3/3.1/3.1 - Backlog.md` (Épica 5), `docs/V3/3.1/3.1 Documento tecnico.md`, user Epic 3.1.C spec.

---

## Implemented

### 1. Traceability summary (domain + report)

- **`src/domain/traceability.py`**
  - Documented diagnostic policy: `traceability_warning` is report + API only; not persisted to `pallet_results`.
  - Added `ALL_TRACEABILITY_STATUSES` and `compute_traceability_summary(entities) -> Dict[str, int]` with keys: `total_entities`, `valid`, `missing`, `invalid`, `unvalidated`. Legacy entities without `traceability_status` are counted as `missing`.

- **`src/reporting/hybrid_report.py`**
  - Report dict now includes `traceability_summary` (result of `compute_traceability_summary(entities)`). Backward compatible: reports without traceability still build; summary reflects counts.

### 2. API: list_entities enrichment and filter

- **`src/api/schemas/responses.py`**
  - `EntitiesListResponse` extended with optional `traceability_summary: Optional[TraceabilitySummary]` (typed model: total_entities, valid, missing, invalid, unvalidated).

- **`src/api/routes/entities.py`**
  - `GET /jobs/{job_id}/entities`:
    - Optional query param `traceability_status` (valid | missing | invalid | unvalidated). Invalid value returns 422.
    - Response includes `traceability_summary` always as full-job summary (from report or computed from full entity list when absent).

### 3. Export/report CSV enrichment

- **`src/reporting/artifacts.py`**
  - `write_report_csv(path, report)` added (Epic 3.1.C). Writes one row per entity with columns: `entity_uid`, `pallet_id`, `entity_type`, `count_status`, `final_quantity`, `internal_code`, `confidence`, `source_image_id`, `traceability_status`, `traceability_warning`. Empty entities produce header-only file. Backward compatible: entities without traceability get empty cells.

- **`src/pipeline/stages/reporting_stage.py`**
  - After writing `hybrid_report.json`, writes `hybrid_report.csv` via `write_report_csv(csv_path, report)`. Worker already references `report_csv_path`; CSV is now produced.

- **`src/reporting/__init__.py`**
  - Exported `write_report_csv`.

### 4. Diagnostic policy

- **`src/domain/traceability.py`**
  - Module docstring states: `traceability_warning` is diagnostic only (report + API); not persisted. Persisted fields: `source_image_id`, `traceability_status` only.

### 5. Tests

- **`tests/test_epic_3_1_c.py`**
  - `compute_traceability_summary`: counts by status, empty list, legacy entities without status.
  - `build_hybrid_report`: includes `traceability_summary`; backward compat when entities have no traceability.
  - `write_report_csv`: includes traceability columns; empty entities; backward compat when entities lack traceability fields.
  - **list_entities API:** traceability_summary always full-job (with/without filters); typed TraceabilitySummary; invalid traceability_status filter returns 422; valid filter; legacy report without summary computed from full entity list.

---

## Backward compatibility

- Reports without `traceability_summary` (e.g. from older runs): `list_entities` computes summary from entity list when needed.
- Entities without `traceability_status`: counted as `missing` in summary; CSV gets empty cells.
- No schema or API breaking changes; all new fields optional.

---

## Left for future work

- Frontend UI for traceability summary and filter.
- Full multi-evidence (`source_image_ids`, `primary_image_id`).
- Evidence-quality scoring.
- Advanced metrics dashboards.

---

## Verification

- Run: `pytest tests/test_epic_3_1_c.py -v`
- After a job run, `hybrid_report.json` should contain `traceability_summary` and `hybrid_report.csv` should have `source_image_id`, `traceability_status`, `traceability_warning` columns.
- `GET /api/v1/inventory/jobs/{job_id}/entities` returns `traceability_summary` when report has it; `?traceability_status=missing` filters the list.
