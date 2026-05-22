# Use Cases Modularization Audit

## 1. Executive summary

**Status:** AUDIT_ONLY

The backend application layer exposes **74 Python modules** (plus `__init__.py`) in a single flat directory: `backend/src/application/use_cases/`. Together they implement roughly **80+ use case classes** (several files define multiple classes). The folder is the central orchestration layer for v3 inventories, aisles, capture/ingestion sessions, reviews, clients/suppliers, jobs, analytics compare/export, and internal pipeline persistence.

Navigation and ownership are difficult because:

- All files share one namespace with inconsistent naming (`get_*`, `list_*`, `create_*`, `run_*`, `manage_*`, `compute_*`, `materialize_*`, `export_*`, `backfill_*`).
- Cross-cutting helpers (`review_validation.py`, `benchmark_compare_support.py`, `capture_session_group_assignment_guard.py`) sit beside full use cases.
- Import wiring is duplicated: `api/dependencies.py` imports ~50 modules at module top level, and **10 v3 route modules** import use cases directly again (partial overlap with dependencies).
- The package barrel (`__init__.py`) exports only **2** symbols while the rest of the codebase imports concrete modules — the barrel is stale and misleading.

Overall architecture is **sound at the port boundary** (repositories, capture ports, clock, scanner ports). Violations are localized (config/settings reads, one infrastructure import, pipeline provider registry in a supplier module, large multi-class files). Modularization can proceed **incrementally** without behavior changes.

**Recommendation after audit:** `READY_WITH_RISKS` — safe to start **Phase 2 (move files + update imports only)** once import surfaces are scripted and CI commands are run per step.

---

## 2. Current structure

**Actual path:** `backend/src/application/use_cases/` (not `use-cases` at repo root).

```
backend/src/application/use_cases/
├── __init__.py                          # exports 2 symbols only
├── assign_capture_session_group_to_existing_aisle.py
├── backfill_inventory_statuses.py
├── backfill_legacy_aisles.py
├── backfill_legacy_client_supplier_defaults.py
├── benchmark_compare_support.py         # shared helper, not a UseCase
├── cancel_aisle_job.py
├── cancel_capture_session.py
├── capture_session_group_assignment_guard.py  # shared guard helpers
├── close_capture_session.py
├── compare_aisle_runs.py
├── compare_many_aisle_runs.py
├── compute_capture_session_assignment_preview.py
├── compute_capture_session_groups.py
├── compute_materialized_capture_session_group_preview.py
├── confirm_position.py
├── create_aisle.py
├── create_aisle_and_assign_capture_session_group.py
├── create_capture_session.py
├── create_client.py
├── create_client_supplier.py
├── create_inventory.py
├── delete_aisle_source_asset.py
├── delete_position.py
├── export_aisle_benchmark.py            # 2 use case classes
├── export_aisle_code_scans.py
├── export_inventory_business.py         # 3 use case classes
├── export_inventory_results.py            # 2 use case classes
├── get_aisle_code_scan_review_signals.py
├── get_aisle_merge_results.py
├── get_aisle_processing_status.py
├── get_capture_session_detail.py
├── get_capture_session_groups.py
├── get_client.py
├── get_client_supplier.py
├── get_inventory.py
├── get_inventory_metrics.py
├── get_position_code_scan_evidence.py
├── get_position_detail.py
├── list_aisle_assets.py
├── list_aisle_code_scans.py
├── list_aisle_jobs.py
├── list_aisle_positions.py
├── list_aisles_by_inventory.py
├── list_aisles_with_status.py
├── list_capture_sessions.py
├── list_client_suppliers.py
├── list_clients.py
├── list_inventories.py
├── list_inventory_list_items.py
├── list_review_queue.py
├── manage_supplier_prompt_configs.py      # 5 use case classes
├── manage_supplier_reference_images.py    # 2 use case classes
├── mark_position_image_mismatch.py
├── mark_position_unknown.py
├── match_aisle_code_scan_detections.py
├── materialize_capture_session.py
├── materialize_capture_session_group.py
├── persist_aisle_result.py                # pipeline-internal
├── promote_aisle_operational_job.py
├── recompute_consolidated_counts.py       # shared consolidation orchestration
├── resolve_aisle_job_for_inventory_read.py
├── retry_aisle_job.py
├── review_validation.py                   # shared validation, not a UseCase
├── run_aisle_code_scan.py
├── run_aisle_merge.py
├── start_aisle_processing.py
├── summarize_aisle_code_scans.py
├── update_capture_session_clock_offset.py
├── update_position_code.py
├── update_product_quantity.py
├── update_product_sku.py
├── upload_aisle_assets.py
├── upload_capture_session_staging_items.py
└── upload_supplier_reference_images.py    # 2 use case classes
```

**Counts**

| Metric | Value |
|--------|------:|
| Top-level `.py` files (excl. `__init__`) | 74 |
| Dedicated test modules under `backend/tests/application/use_cases/` | 62 |
| Internal cross-imports between use_case modules | 24 import lines across 20 files |
| Estimated use case classes (`class *UseCase`) | ~80 |

### Area summary table

| Area | Files | Notes |
|------|------:|-------|
| Inventories | 9 | CRUD, metrics, exports, status backfill |
| Aisles | 22 | Jobs, merge, code scans, assets, processing |
| Positions / review | 11 | Includes `review_validation.py` helper |
| Capture / ingestion sessions | 16 | Largest files; G4–G7 grouping/materialize flows |
| Clients | 3 | Small, stable |
| Client suppliers & prompts | 6 | Multi-class files (`manage_*`, `upload_*`) |
| Analytics / compare / benchmark | 4 | `benchmark_compare_support` is shared logic |
| Jobs / pipeline (non-HTTP) | 2 | `persist_aisle_result`, `recompute_consolidated_counts` |
| Shared helpers (misplaced) | 3 | Should move to `shared/` in target layout |
| Package barrel | 1 | Under-exports vs real usage |

---

## 3. Main findings

### HIGH

| File(s) | Issue | Impact | Recommendation |
|---------|-------|--------|----------------|
| `api/dependencies.py` (lines 53–134+) | **Monolithic import block** of ~50 use case modules at import time | Any package move breaks startup unless all paths updated; slow coupling surface | Treat `dependencies.py` as primary registry; generate import map in Phase 2; consider lazy/local imports only in factory functions (already partially done for capture session factories ~L1230+) |
| All v3 routes + `dependencies.py` | **Dual import surfaces**: routes import use cases directly *and* via `Depends(get_*_use_case)` from dependencies | Miss one site → `ImportError` at runtime | Phase 2: mechanical rewrite with `rg`/script; optional follow-up to route-only-via-dependencies |
| `__init__.py` | Exports only `CreateInventory*` and `ListInventories*` | Suggests incomplete public API; unused for most wiring | Either expand barrel intentionally in Phase 3 or document as legacy; do not rely on it today |
| `run_aisle_code_scan.py` | Imports `src.infrastructure.code_scanning.image_decode` | **Layer violation**: application → infrastructure | Move image decode behind `SourceAssetContentReader` / `CodeScannerPort` adapter or an application port; until then keep file in `code_scans/` and document exception |

### MEDIUM

| File(s) | Issue | Impact | Recommendation |
|---------|-------|--------|----------------|
| `review_validation.py` | Shared policy module named like a use case | Confusing ownership; 8 review modules depend on it | Move to `use_cases/shared/review_validation.py` (Phase 2–4) |
| `benchmark_compare_support.py` | 303 lines; CSV/diff helpers + types | Used by `compare_aisle_runs`, `compare_many_aisle_runs`, `export_aisle_benchmark` | `shared/benchmark_compare_support.py` or `application/services/benchmark_compare` after imports stable |
| `capture_session_group_assignment_guard.py` | Guard functions, not a class | Same as above | `capture_sessions/guards.py` or `shared/capture_session_guards.py` |
| `manage_supplier_prompt_configs.py` | **5 use case classes** in one file (363 lines) | Hard to review/test in isolation | Split in Phase 5 only; keep file path stable until then |
| `export_inventory_business.py` | **3 export use cases** + heavy service orchestration (244 lines) | Mixed export orchestration | Module `exports/` or split per export type in Phase 5 |
| `materialize_capture_session_group.py` (478), `compute_materialized_capture_session_group_preview.py` (504), `upload_capture_session_staging_items.py` (446) | Very large modules | Higher regression risk when touching | No split until after folder move; add characterization tests where missing |
| `compare_many_aisle_runs.py` → `benchmark_compare_support.py` | Use case imports use case helper | Establishes **internal DAG** within folder | Acceptable short-term; document allowed edges: `shared` must not import sibling feature modules |
| `run_aisle_code_scan.py`, `start_aisle_processing.py` | `load_settings()` from `src.config` | Config coupling outside ports | Inject settings via constructor or `AppContainer` in later phase |
| `manage_supplier_prompt_configs.py` | Imports `src.pipeline.providers.definitions` | Application layer knows pipeline registry | Acceptable for provider catalog validation; consider `application/services/provider_catalog` |

### LOW

| File(s) | Issue | Impact | Recommendation |
|---------|-------|--------|----------------|
| Naming | Mix of verbs: `get_`, `list_`, `create_`, `run_`, `compute_`, `materialize_`, `export_`, `backfill_` | Predictability only | Keep filenames on move; optional rename in Phase 5 |
| `list_aisles_by_inventory.py` vs `list_aisles_with_status.py` | Overlapping aisle list concerns | Minor discovery friction | Same `aisles/` module, document distinction in module README |
| `get_aisle_processing_status.py` | Exposes `AisleProcessingStatusResult` dataclass consumed by routes | Blurs application DTO vs API schema | Acceptable; could move to `application/dto` later |
| `backfill_*.py` (3 files) | Operational scripts also live at `src/backfill_*.py` | Two entry points to same use cases | Document; not part of HTTP modularization |

---

## 4. Proposed module structure

Proposed target tree (Python packages; each folder gets `__init__.py` for explicit re-exports in Phase 3):

```
backend/src/application/use_cases/
├── __init__.py                 # optional thin re-exports only
├── shared/
│   ├── __init__.py
│   ├── review_validation.py
│   ├── benchmark_compare_support.py
│   └── capture_session_group_assignment_guard.py
├── inventories/
│   ├── __init__.py
│   ├── create_inventory.py
│   ├── get_inventory.py
│   ├── list_inventories.py
│   ├── list_inventory_list_items.py
│   ├── get_inventory_metrics.py
│   ├── backfill_inventory_statuses.py
│   ├── export_inventory_results.py
│   └── export_inventory_business.py
├── aisles/
│   ├── __init__.py
│   ├── create_aisle.py
│   ├── list_aisles_by_inventory.py
│   ├── list_aisles_with_status.py
│   ├── get_aisle_processing_status.py
│   ├── start_aisle_processing.py
│   ├── cancel_aisle_job.py
│   ├── retry_aisle_job.py
│   ├── list_aisle_jobs.py
│   ├── promote_aisle_operational_job.py
│   ├── resolve_aisle_job_for_inventory_read.py
│   ├── run_aisle_merge.py
│   ├── get_aisle_merge_results.py
│   ├── upload_aisle_assets.py
│   ├── list_aisle_assets.py
│   ├── delete_aisle_source_asset.py
│   └── backfill_legacy_aisles.py
├── positions/
│   ├── __init__.py
│   ├── list_aisle_positions.py
│   ├── get_position_detail.py
│   ├── get_position_code_scan_evidence.py
│   ├── confirm_position.py
│   ├── delete_position.py
│   ├── update_position_code.py
│   ├── update_product_quantity.py
│   ├── update_product_sku.py
│   ├── mark_position_unknown.py
│   ├── mark_position_image_mismatch.py
│   └── list_review_queue.py
├── clients/
│   ├── __init__.py
│   ├── create_client.py
│   ├── get_client.py
│   └── list_clients.py
├── suppliers/
│   ├── __init__.py
│   ├── create_client_supplier.py
│   ├── get_client_supplier.py
│   ├── list_client_suppliers.py
│   ├── manage_supplier_prompt_configs.py
│   ├── manage_supplier_reference_images.py
│   ├── upload_supplier_reference_images.py
│   └── backfill_legacy_client_supplier_defaults.py
├── capture_sessions/
│   ├── __init__.py
│   ├── create_capture_session.py
│   ├── close_capture_session.py
│   ├── cancel_capture_session.py
│   ├── list_capture_sessions.py
│   ├── get_capture_session_detail.py
│   ├── upload_capture_session_staging_items.py
│   ├── update_capture_session_clock_offset.py
│   ├── compute_capture_session_assignment_preview.py
│   ├── compute_capture_session_groups.py
│   ├── get_capture_session_groups.py
│   ├── assign_capture_session_group_to_existing_aisle.py
│   ├── create_aisle_and_assign_capture_session_group.py
│   ├── compute_materialized_capture_session_group_preview.py
│   ├── materialize_capture_session.py
│   └── materialize_capture_session_group.py
├── code_scans/
│   ├── __init__.py
│   ├── run_aisle_code_scan.py
│   ├── list_aisle_code_scans.py
│   ├── summarize_aisle_code_scans.py
│   ├── match_aisle_code_scan_detections.py
│   ├── get_aisle_code_scan_review_signals.py
│   └── export_aisle_code_scans.py
├── analytics/
│   ├── __init__.py
│   ├── compare_aisle_runs.py
│   ├── compare_many_aisle_runs.py
│   └── export_aisle_benchmark.py
└── pipeline/
    ├── __init__.py
    ├── persist_aisle_result.py
    └── recompute_consolidated_counts.py
```

**Dependency rule for modules:** `shared/` must not import from feature folders. Feature folders may import `shared/`. `pipeline/` may be imported by infrastructure only (today: `v3_job_executor.py` imports `persist_aisle_result` and `recompute_consolidated_counts`).

---

## 5. File mapping proposal

| Current file | Proposed location | Reason |
|--------------|-------------------|--------|
| `review_validation.py` | `shared/review_validation.py` | Shared position/job validation |
| `benchmark_compare_support.py` | `shared/benchmark_compare_support.py` | Compare/export helper types |
| `capture_session_group_assignment_guard.py` | `shared/capture_session_group_assignment_guard.py` | G4 guard preconditions |
| `create_inventory.py` | `inventories/create_inventory.py` | Inventory aggregate |
| `get_inventory.py` | `inventories/get_inventory.py` | Inventory aggregate |
| `list_inventories.py` | `inventories/list_inventories.py` | Inventory aggregate |
| `list_inventory_list_items.py` | `inventories/list_inventory_list_items.py` | Inventory list projection |
| `get_inventory_metrics.py` | `inventories/get_inventory_metrics.py` | Inventory metrics |
| `backfill_inventory_statuses.py` | `inventories/backfill_inventory_statuses.py` | Inventory maintenance |
| `export_inventory_results.py` | `inventories/export_inventory_results.py` | Inventory-scoped export |
| `export_inventory_business.py` | `inventories/export_inventory_business.py` | Inventory package export |
| `create_aisle.py` | `aisles/create_aisle.py` | Aisle lifecycle |
| `list_aisles_by_inventory.py` | `aisles/list_aisles_by_inventory.py` | Aisle listing |
| `list_aisles_with_status.py` | `aisles/list_aisles_with_status.py` | Aisle listing with status |
| `get_aisle_processing_status.py` | `aisles/get_aisle_processing_status.py` | Job status read model |
| `start_aisle_processing.py` | `aisles/start_aisle_processing.py` | Processing kickoff |
| `cancel_aisle_job.py` | `aisles/cancel_aisle_job.py` | Job control |
| `retry_aisle_job.py` | `aisles/retry_aisle_job.py` | Job control |
| `list_aisle_jobs.py` | `aisles/list_aisle_jobs.py` | Job listing |
| `promote_aisle_operational_job.py` | `aisles/promote_aisle_operational_job.py` | Operational promotion |
| `resolve_aisle_job_for_inventory_read.py` | `aisles/resolve_aisle_job_for_inventory_read.py` | Job resolution for reads |
| `run_aisle_merge.py` | `aisles/run_aisle_merge.py` | Merge orchestration |
| `get_aisle_merge_results.py` | `aisles/get_aisle_merge_results.py` | Merge read |
| `upload_aisle_assets.py` | `aisles/upload_aisle_assets.py` | Source assets |
| `list_aisle_assets.py` | `aisles/list_aisle_assets.py` | Source assets |
| `delete_aisle_source_asset.py` | `aisles/delete_aisle_source_asset.py` | Source assets |
| `backfill_legacy_aisles.py` | `aisles/backfill_legacy_aisles.py` | Legacy migration |
| `list_aisle_positions.py` | `positions/list_aisle_positions.py` | Position reads |
| `get_position_detail.py` | `positions/get_position_detail.py` | Position reads |
| `get_position_code_scan_evidence.py` | `positions/get_position_code_scan_evidence.py` | Review evidence |
| `confirm_position.py` | `positions/confirm_position.py` | Review mutations |
| `delete_position.py` | `positions/delete_position.py` | Review mutations |
| `update_position_code.py` | `positions/update_position_code.py` | Review mutations |
| `update_product_quantity.py` | `positions/update_product_quantity.py` | Review mutations |
| `update_product_sku.py` | `positions/update_product_sku.py` | Review mutations |
| `mark_position_unknown.py` | `positions/mark_position_unknown.py` | Review mutations |
| `mark_position_image_mismatch.py` | `positions/mark_position_image_mismatch.py` | Review mutations |
| `list_review_queue.py` | `positions/list_review_queue.py` | Review queue |
| `create_client.py` | `clients/create_client.py` | Client CRUD |
| `get_client.py` | `clients/get_client.py` | Client CRUD |
| `list_clients.py` | `clients/list_clients.py` | Client CRUD |
| `create_client_supplier.py` | `suppliers/create_client_supplier.py` | Supplier under client |
| `get_client_supplier.py` | `suppliers/get_client_supplier.py` | Supplier under client |
| `list_client_suppliers.py` | `suppliers/list_client_suppliers.py` | Supplier under client |
| `manage_supplier_prompt_configs.py` | `suppliers/manage_supplier_prompt_configs.py` | Prompt config |
| `manage_supplier_reference_images.py` | `suppliers/manage_supplier_reference_images.py` | Reference images |
| `upload_supplier_reference_images.py` | `suppliers/upload_supplier_reference_images.py` | Reference images |
| `backfill_legacy_client_supplier_defaults.py` | `suppliers/backfill_legacy_client_supplier_defaults.py` | Legacy migration |
| `create_capture_session.py` | `capture_sessions/create_capture_session.py` | Ingestion session |
| `close_capture_session.py` | `capture_sessions/close_capture_session.py` | Ingestion session |
| `cancel_capture_session.py` | `capture_sessions/cancel_capture_session.py` | Ingestion session |
| `list_capture_sessions.py` | `capture_sessions/list_capture_sessions.py` | Ingestion session |
| `get_capture_session_detail.py` | `capture_sessions/get_capture_session_detail.py` | Ingestion session |
| `upload_capture_session_staging_items.py` | `capture_sessions/upload_capture_session_staging_items.py` | Staging upload |
| `update_capture_session_clock_offset.py` | `capture_sessions/update_capture_session_clock_offset.py` | Session metadata |
| `compute_capture_session_assignment_preview.py` | `capture_sessions/compute_capture_session_assignment_preview.py` | G4/G6 preview |
| `compute_capture_session_groups.py` | `capture_sessions/compute_capture_session_groups.py` | Grouping |
| `get_capture_session_groups.py` | `capture_sessions/get_capture_session_groups.py` | Grouping read |
| `assign_capture_session_group_to_existing_aisle.py` | `capture_sessions/assign_capture_session_group_to_existing_aisle.py` | G4 assign |
| `create_aisle_and_assign_capture_session_group.py` | `capture_sessions/create_aisle_and_assign_capture_session_group.py` | G4 create+assign |
| `compute_materialized_capture_session_group_preview.py` | `capture_sessions/compute_materialized_capture_session_group_preview.py` | G6 preview |
| `materialize_capture_session.py` | `capture_sessions/materialize_capture_session.py` | G5 materialize |
| `materialize_capture_session_group.py` | `capture_sessions/materialize_capture_session_group.py` | G5 materialize group |
| `run_aisle_code_scan.py` | `code_scans/run_aisle_code_scan.py` | Code scan feature |
| `list_aisle_code_scans.py` | `code_scans/list_aisle_code_scans.py` | Code scan feature |
| `summarize_aisle_code_scans.py` | `code_scans/summarize_aisle_code_scans.py` | Code scan feature |
| `match_aisle_code_scan_detections.py` | `code_scans/match_aisle_code_scan_detections.py` | Code scan feature |
| `get_aisle_code_scan_review_signals.py` | `code_scans/get_aisle_code_scan_review_signals.py` | Code scan feature |
| `export_aisle_code_scans.py` | `code_scans/export_aisle_code_scans.py` | Code scan export |
| `compare_aisle_runs.py` | `analytics/compare_aisle_runs.py` | Analytics compare |
| `compare_many_aisle_runs.py` | `analytics/compare_many_aisle_runs.py` | Analytics compare-many |
| `export_aisle_benchmark.py` | `analytics/export_aisle_benchmark.py` | Benchmark export |
| `persist_aisle_result.py` | `pipeline/persist_aisle_result.py` | CV pipeline persistence |
| `recompute_consolidated_counts.py` | `pipeline/recompute_consolidated_counts.py` | Consolidation recompute |

---

## 6. Import impact analysis

**Primary rule:** Every `from src.application.use_cases.<module> import ...` must become `from src.application.use_cases.<package>.<module> import ...` (or re-export from package `__init__.py`).

| Importing area | Impact | Notes |
|----------------|--------|-------|
| `backend/src/api/dependencies.py` | **Critical** | ~50 top-level imports + lazy imports inside `get_*_use_case` factories for capture sessions |
| `backend/src/api/routes/v3/aisles.py` | High | 16 direct use case imports |
| `backend/src/api/routes/v3/capture_sessions.py` | High | 15 direct imports |
| `backend/src/api/routes/v3/clients.py` | High | 12 direct imports (incl. multi-class modules) |
| `backend/src/api/routes/v3/reviews.py` | Medium | 7 imports (overlap with dependencies) |
| `backend/src/api/routes/v3/shared.py` | Medium | 8 imports + `AisleProcessingStatusResult` type |
| `backend/src/api/routes/v3/inventories.py` | Medium | 6 imports |
| `backend/src/api/routes/v3/code_scans.py` | Medium | Commands + use cases |
| `backend/src/api/routes/v3/assets.py` | Low | 3 imports |
| `backend/src/api/routes/v3/positions.py` | Low | 3 imports |
| `backend/src/api/routes/v3/analytics_api.py` | Low | 1 import |
| `backend/src/api/routes/v3/review_queue.py` | Low | 1 import |
| `backend/src/api/schemas/capture_schemas.py` | Low | Imports preview command types from use case module |
| `backend/tests/application/use_cases/*.py` | High | 62 test files — same path rewrite |
| `backend/tests/api/*.py` | Medium | Several API tests import use cases |
| `backend/tests/infrastructure/pipeline/*.py` | Medium | `persist_aisle_result`, `recompute_consolidated_counts` |
| `backend/src/infrastructure/pipeline/v3_job_executor.py` | Medium | Pipeline orchestration imports |
| `backend/src/backfill_*.py` (3 scripts) | Low | CLI backfill entry points |
| `backend/src/runtime/container/use_case_builders.py` | Low | `recompute_consolidated_counts` |
| `backend/src/application/services/analytics_cost_summary_service.py` | Low | Compare use case types |
| `backend/src/application/use_cases/*` (internal) | Medium | 24 cross-imports must be updated together |

**Estimated import statements to touch:** ~200–280 (grep shows 40+ files referencing `application.use_cases`; many files have multiple import lines).

**Mitigation:** Use a one-shot codemod:

```bash
# Example (verify before running):
rg -l 'from src\.application\.use_cases\.([a-z_]+) import' backend \
  | xargs sed -i '' 's/from src.application.use_cases.\([a-z_]*\)/from src.application.use_cases.<pkg>.\1/g'
```

…after producing a CSV mapping `<module> → <pkg>` from Section 5. Prefer `python -m compileall backend` + `pytest` over manual sed for cross-module edges (`review_validation`, `benchmark_compare_support`, etc.).

---

## 7. SOLID / architecture review

### Single Responsibility Principle

- **Generally respected** at class level: each `*UseCase` orchestrates one user-facing or pipeline action.
- **Violations at file level:**
  - `manage_supplier_prompt_configs.py`: five use cases (create, list, get, get active, activate).
  - `export_inventory_business.py`: three export use cases plus ZIP/CSV orchestration.
  - `export_inventory_results.py`, `export_aisle_benchmark.py`, `upload_supplier_reference_images.py`, `manage_supplier_reference_images.py`: two classes each.
  - `benchmark_compare_support.py`: pure functions + dataclasses (~303 lines) — not a use case but lives in the folder.

### Dependency Inversion

- **Strong pattern:** Constructors take `*Repository`, `*Port`, `Clock`, `MetricsCalculator`, etc. from `application.ports`.
- **Application services** (`aisle_inventory_scope`, `inventory_status_reconciler`, `csv_inventory_exporter`, …) are composed in `__init__` — acceptable orchestration layer thickness.
- **Leaks:**
  - `run_aisle_code_scan.py` → `src.infrastructure.code_scanning.image_decode` (concrete infra).
  - `manage_supplier_prompt_configs.py` → `src.pipeline.providers.definitions` (provider registry).
  - `run_aisle_code_scan.py`, `start_aisle_processing.py` → `load_settings()` (global config).

### Separation application / infrastructure / HTTP

- **No FastAPI** `Request`/`Response` or `HTTPException` in use case modules (verified: no matches).
- **No SQLAlchemy** session usage in use cases (verified).
- **HTTP-adjacent:** `review_validation.ensure_review_job_matches_position` raises `ValueError` mapped to 422 in routes — documented contract, acceptable.
- **Pipeline-only:** `persist_aisle_result.py` invoked from `v3_job_executor.py`, not from API dependencies.

### Shared validation / policy reuse

- **Good:** `review_validation.py` centralizes position resolution and job-id matching for review flows.
- **Good:** `require_aisle_scoped_to_inventory` used widely from `application.services`.
- **Risk:** `recompute_consolidated_counts` imported from `run_aisle_merge`, `persist_aisle_result`, `backfill_legacy_aisles` — correct function reuse but creates **internal coupling**; moving to `pipeline/` makes the dependency explicit.

### Internal import graph (use_cases → use_cases)

| From | To | Nature |
|------|-----|--------|
| Review modules (8) | `review_validation` | Shared policy |
| `export_aisle_benchmark` | `benchmark_compare_support`, `compare_aisle_runs` | Export builds on compare |
| `compare_many_aisle_runs`, `compare_aisle_runs` | `benchmark_compare_support` | Shared compare helpers |
| Capture G4/G5/G6 (5) | `capture_session_group_assignment_guard` | Shared guard |
| `create_aisle_and_assign_*`, `assign_*` | `create_aisle`, `get_capture_session_groups` | Orchestration composition |
| `run_aisle_code_scan` | `match_aisle_code_scan_detections` | Scan delegates matching |
| Consolidation (3) | `recompute_consolidated_counts` | Shared recompute |

No circular imports detected in static review (guards/helpers are leaves; compare modules do not import capture or review modules).

---

## 8. Refactor plan

### Phase 1 — Read-only audit and grouping proposal (this document)

- **Goal:** Agree module boundaries and import blast radius.
- **Files affected:** None (documentation only).
- **Risk:** None.
- **Validation:** Review with team.
- **Rollback:** N/A.

### Phase 2 — Add folder structure; move files; update imports only

- **Goal:** Physical modularization without logic edits.
- **Files affected:** All 74 modules + ~40 importer files + internal cross-imports.
- **Risk:** Medium — missed import causes runtime `ImportError`.
- **Validation commands:**

```bash
python -m compileall backend
cd backend && ruff check .
cd backend && mypy .
pytest
```

- **Rollback:** Single revert commit; no data migration.

**DoD:** All tests pass; API starts; grep shows zero imports of old flat paths.

### Phase 3 — Module-level `__init__.py` re-exports (optional)

- **Goal:** Stabilize import paths for common symbols (e.g. `from src.application.use_cases.inventories import CreateInventoryUseCase`).
- **Files affected:** Each new package `__init__.py`; optionally slim `dependencies.py` imports.
- **Risk:** Low — circular import if `__init__.py` eagerly imports everything.
- **Validation:** Same as Phase 2; add `python -c "from src.application.use_cases.inventories import CreateInventoryUseCase"`.
- **Rollback:** Remove re-exports; keep explicit submodule imports.

**Recommendation:** Use **explicit submodule imports** in `dependencies.py` (clearer for DI). Use `__init__.py` only for stable public subsets if needed.

### Phase 4 — Extract shared helpers (no behavior change)

- **Goal:** Move `review_validation`, `benchmark_compare_support`, `capture_session_group_assignment_guard` into `shared/` (already relocated in Phase 2); optionally move thin wrappers to `application/services` if duplicates exist.
- **Risk:** Low if Phase 2 import map is correct.
- **Validation:** Targeted tests for review, compare, capture G4/G5/G6 flows.
- **Rollback:** Move files back.

### Phase 5 — Split oversized files & naming cleanup

- **Goal:** Split multi-class files; address `load_settings` / infrastructure import in `run_aisle_code_scan`.
- **Files affected:** `manage_supplier_prompt_configs.py`, export modules, largest capture session files.
- **Risk:** High — logic refactor surface.
- **Validation:** Full `pytest` + manual smoke on capture session + export + supplier admin APIs.
- **Rollback:** Per-file revert; do not combine with Phase 2 in same release without tests.

---

## 9. Recommended first implementation phase

**Execute Phase 2 only** (move + imports):

1. Create packages: `shared`, `inventories`, `aisles`, `positions`, `clients`, `suppliers`, `capture_sessions`, `code_scans`, `analytics`, `pipeline`.
2. `git mv` each file per Section 5 mapping (preserves history).
3. Update imports using scripted mapping + manual pass for internal cross-imports (`shared.*`).
4. Run validation stack from repo root / CI parity:

```bash
python -m compileall backend
cd backend && ruff check .
cd backend && mypy .
pytest
```

5. Do **not** split multi-class files or fix layer violations in the same PR.

---

## 10. Definition of Done for the audit

- [x] All 74 use-case modules inspected (flat layout inventoried).
- [x] Every file has a proposed module or explicit shared/pipeline placement.
- [x] Import risks identified (`dependencies.py`, routes, tests, pipeline, scripts).
- [x] No runtime application code changed during audit.
- [x] Markdown report created at `audit/use-cases-modularization-audit.md`.

---

## Validation commands (for future implementation phases)

From repository configuration (verified):

| Command | Where defined | Purpose |
|---------|---------------|---------|
| `python -m compileall backend` | CI workflow | Syntax / import paths |
| `ruff check .` | `.github/workflows/*-quality-gate.yml` (run from `backend/`) | Lint |
| `mypy .` | CI workflow (run from `backend/`) | Type check |
| `pytest` | `pytest.ini` at repo root (`testpaths = backend/tests`, `pythonpath = backend`) | Tests with coverage |

Frontend commands (`npm run test`, etc.) are **out of scope** for this use-case move.

Optional local audit tools mentioned in `pyproject.toml` dev deps: `import-linter`, `grimp` — not wired in CI; useful to add a contract after Phase 2:

```bash
# Example future check (configure contracts first)
import-linter --config importlinter.ini
```

---

## Open questions

1. **Package barrel:** Should `application.use_cases.__init__` re-export all use cases used by `dependencies.py`, or remain minimal / deprecated?
2. **Route imports:** Should Phase 2 also remove duplicate direct use case imports from route modules (only `Depends`), or only update paths?
3. **`pipeline/` placement:** Is `persist_aisle_result` considered application layer permanently, or should it move to `application/pipeline/` outside `use_cases/`?
4. **`list_aisles_by_inventory` vs `list_aisles_with_status`:** Merge into one module in a later phase, or keep separate permanently?
5. **Import-linter contracts:** Are there existing architecture contracts (e.g. `application` must not import `infrastructure`) enforced in CI beyond ad-hoc review?

---

## Final recommendation

**`READY_WITH_RISKS`**

The codebase is ready for a **move-only modularization** (Phase 2) with scripted import updates and full CI validation. Reserve file splits and layer fixes for Phase 5. The highest risk is incomplete import rewrites in `api/dependencies.py` and v3 route modules; the highest architectural debt is `run_aisle_code_scan.py` importing infrastructure directly (fix separately from folder moves).
