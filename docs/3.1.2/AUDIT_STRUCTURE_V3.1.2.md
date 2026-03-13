# AUDIT_STRUCTURE_V3.1.2.md

## 1. Summary

This document reports the directory structure audit for Dinamic Inventory v3.1.2. It describes current backend and frontend layout, identifies mixed responsibilities and weak boundaries, and proposes realistic target structures and risks.

## 2. Scope

- **Included:** Backend tree under `src/`; frontend tree under `frontend/src/`. No file moves or renames were performed.

## 3. Findings

### 3.1 Backend structure (current)

```
src/
  api/           — routes, schemas, dependencies, server, photos_handler
  application/   — ports (repositories, clock, contracts, services), use_cases
  domain/        — entities (aisle, assets, evidence, inventory, jobs, positions, products, reviews), traceability, entity, pallet
  infrastructure/— repositories (memory + sql), pipeline (v3_job_executor, v3_report_mapper), queue, storage, adapters (clock), services
  runtime/       — v3_deps (wiring of repos and use cases)
  config.py      — settings
  database/      — repository (Stage 8: jobs, pallet_results, job_events), schema.sql, sqlserver
  jobs/          — queue, worker, job_store, models, adapters, ports, photos_paths, image_identity
  pipeline/      — hybrid_inventory_pipeline, stages, execution_log, context, contracts, adapters
  frames/        — normalize, sources, types
  reporting/     — hybrid_report, artifacts, display_label
  ... (detection, tracking, reid, video, llm, parsing, etc.)
```

**Observations:**
- **Layers:** API → application (use cases + ports) → domain; infrastructure implements ports. Clear for v3 flow.
- **Mixed:** `database/repository.py` is Stage 8 (legacy jobs/pallet_results/events); `infrastructure/repositories/sql_*.py` are v3. Two persistence styles in one tree. **Transitional.**
- **jobs/:** Contains both queue/worker (runtime) and job_store (legacy DB) and photo path helpers. Coupling to legacy pipeline and to v3 executor (worker calls executor). **Mixed responsibility.**
- **Pipeline:** Under `src/pipeline/` and `src/infrastructure/pipeline/` (v3_report_mapper, v3_job_executor). Executor is infrastructure; pipeline is domain of execution. **Acceptable** but could be grouped under one parent (e.g. pipeline/ with subdirs) in reorg.
- **No temporary/transitional folders** with obvious names (e.g. "legacy", "old"); legacy lives alongside active in same modules.

### 3.2 Frontend structure (current)

```
frontend/src/
  api/           — client.ts, queryKeys.ts, types/
  pages/         — InventoriesList, InventoryDetail, AislePositionsPage, PositionDetailPage
  features/      — results/ (components, hooks, mappers, selectors, utils, types, constants)
  components/    — ui/, CreateInventoryDialog, CreateAisleDialog, ExecutionLogPanel
  hooks/         — useInventories, useAisles, usePositions, useMutations, index
  utils/         — apiErrors, positionStatus, aisleStatus, jobStatus, formatDate, resultRoutes, traceability
```

**Observations:**
- **Feature boundary:** Only `features/results` is a feature module; inventory and aisle logic live in pages and hooks at top level. **Asymmetry.**
- **Shared vs feature-specific:** components/ui and Create*Dialog/ExecutionLogPanel are shared; results/* is feature-specific. Clear. No confusion.
- **utils:** Flat list of helpers; no grouping by domain. **Minor** (could group status, routing, format).
- **api/** — Single client and types; good. No legacy folder.

### 3.3 Mixed responsibilities (backend)

- **database/repository.py:** Legacy job CRUD and pallet_results/events. Belongs conceptually to "legacy pipeline" or "Stage 8"; could live under `infrastructure/legacy/` or `jobs/persistence/` after reorg. **Candidate for move** when retiring or isolating legacy.
- **jobs/worker.py:** Dispatches to v3 executor first, then legacy pipeline. Single entry point; moving it would require careful dependency handling. **Keep in place** for v3.1.2; document as bridge.

### 3.4 Proposed target structures (incremental)

**Backend (realistic for Stage 4):**
- Keep `api/`, `application/`, `domain/` as-is.
- Group v3 infrastructure: ensure `infrastructure/repositories/`, `infrastructure/pipeline/` (v3 executor + report mapper) are the only v3 persistence/execution; document that `database/` is legacy.
- Optional: introduce `infrastructure/legacy/` and move `database/repository.py` (and optionally schema.sql) there, or leave in place and document. **Risk:** imports and tests reference `src.database`; move requires global replace.

**Frontend (realistic for Stage 7):**
- Keep `api/`, `components/`, `hooks/`, `utils/` at top level.
- Add `features/inventories/` (hooks, components, or pages that are inventory-specific) and `features/aisles/` if desired; or keep pages at top level and only move result-related code under features/results (already done).
- Optional: group utils into `utils/status/`, `utils/routing/`, `utils/format/`. **Low value** for v3.1.2.

### 3.5 Reorganization risks

- **Backend:** Moving `database/` or renaming `jobs/` could break imports in worker, routes, and tests. Recommend one PR per move; run full test suite after each.
- **Frontend:** Moving pages into features or splitting features will touch many imports (App routes, hooks). Do after backend is stable to avoid churn.

## 4. Classification

| Area | Classification | Note |
|------|----------------|------|
| Backend api/application/domain | **Active, clear** | Aligned with layered design |
| infrastructure/repositories | **Active** | v3 SQL + memory |
| infrastructure/pipeline | **Active** | v3 executor, report mapper |
| database/ | **Legacy/transitional** | Stage 8; separate from v3 |
| jobs/ | **Mixed** | Queue + worker + legacy store |
| Frontend features/results | **Active** | Single feature module |
| Frontend pages/hooks | **Active** | Asymmetric vs features |

## 5. Risks

- Large reorg in one PR increases merge and rollback cost. Prefer small, incremental moves.
- Renaming or moving `database/` may break external scripts or docs that reference path or module name.

## 6. Recommendations

- Document in a single "Architecture" or "Structure" doc: (1) v3 layers (api → application → domain + infrastructure), (2) legacy job flow and where it lives (database/, jobs/worker, jobs/job_store), (3) frontend feature boundary (results only today).
- Stage 4: Prefer documenting and clarifying over large moves; move only when removing legacy or when a clear new boundary is agreed.

## 7. Candidate next-stage actions

- **Stage 4 (Backend reorg):** Document structure; optionally move `database/repository.py` to `infrastructure/legacy/repository.py` (or keep in place). Update imports and tests. Do not rename `jobs/` in v3.1.2.
- **Stage 7 (Frontend reorg):** Define target feature list (e.g. inventories, aisles, results); move inventory/aisle-specific code into features if desired; keep api and types centralized.
