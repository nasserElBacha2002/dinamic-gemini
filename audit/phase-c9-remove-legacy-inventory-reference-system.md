# C9 — Remove Legacy Inventory Reference System

## 1. Executive summary

**Status:** READY_FOR_C10

Phase C9 removes the deprecated inventory-scoped visual reference stack (API, application layer, repositories, domain entity, frontend client/UI, and obsolete tests) after the C5.1 strict analyzer confirmed zero legacy rows. A guarded SQL migration drops `inventory_visual_references` when empty. Supplier reference images remain the operational path; shared artifact/file-resolution helpers and historical `reference_usage` / `visual_reference_context` concepts are preserved.

## 2. Safety gate

Values from `audit/raw/phase-c5-legacy-reference-migration-summary.json` (C5.1 strict run used as C9 pre-removal gate):

| Field | Value |
| --- | --- |
| `require_db_mode` | true |
| `db_connected` | true |
| `total_legacy_reference_rows` | 0 |
| `auto_mappable_rows` | 0 |
| `ambiguous_rows` | 0 |
| `missing_storage_rows` | 0 |

Destructive cleanup (DROP TABLE) is allowed under product rules.

## 3. Scope implemented

- **Backend:** Removed legacy inventory visual-reference routes, use cases, repos, domain entity, resolver/lookup/path helpers, container/API wiring, and inventory-specific error codes where obsolete. Renamed generic file helper to `resolve_reference_image_file_response` with supplier wrapper unchanged at HTTP boundary.
- **Database:** Added `0029_drop_inventory_visual_references.sql` with non-empty guard + `DROP TABLE`; removed table from canonical `schema.sql` and from business cleanup table lists.
- **Frontend:** Removed inventory visual-reference API functions, query keys, hooks, types, and deleted inventory-only components (`InventoryReferenceImagesModule`, `ReferenceImagesDrawer`, `useInventoryReferencePreview`).
- **Tests:** Deleted legacy-focused backend tests; added migration guard test, route-absence (404) API test, and `reference_image_mime` unit tests; updated pipeline/executor/error-mapping/stored-artifact tests for supplier-only references.

## 4. Backend removal summary

- **Routes:** No `/api/v3/inventories/{id}/visual-references` handlers registered (`inventories.py`).
- **Removed:** Domain `InventoryVisualReference`, upload/manage use cases, inventory resolver/lookup/path utils, SQL/memory inventory visual reference repositories, `InventoryVisualReferenceRepository` port and container wiring.
- **Errors:** Removed inventory-visual-reference-specific structured codes and `InventoryVisualReferenceNotFoundError` mapping paths tied to removed routes.

## 5. Database migration

- **File:** `backend/src/database/migrations/versions/0029_drop_inventory_visual_references.sql`
- **Behavior:** If the table exists and has any rows, migration raises error `51029` and does not drop; otherwise drops `inventory_visual_references`.
- **Historical migrations:** Older versions that created the table are unchanged (immutable history).

## 6. Frontend removal summary

- **API:** `inventoriesApi.ts` / `client.ts` — no inventory visual-reference endpoints.
- **State:** Removed `queryKeys.inventories.visualReferences` and related mutations/queries (`useMutations`, `useInventories`, `hooks/index`).
- **Types:** Removed `InventoryVisualReference*` interfaces from `responses.ts`.
- **UI:** Deleted inventory-only reference module/drawer/preview hook; supplier reference UI unchanged.
- **Tests:** Removed `ReferenceImagesDrawer.test.tsx`; replaced `CreateInventoryDialog.visualReferences.test.tsx` with `CreateInventoryDialog.creationFlow.test.tsx`.

## 7. Preserved shared/generic pieces

- `supplier_reference_images` table, APIs, and frontend modules remain.
- `ManagedImageAssetsDrawer` and supplier drawers/modules remain.
- `resolve_reference_image_file_response` + `resolve_supplier_reference_image_file_response` for authenticated file serving.
- `WorkerInputArtifactResolver` / `ReferenceImageRecord`, `AnalysisContext.visual_references`, `VisualReferenceContext`, `reference_usage` / `visual_reference_context` in pipeline metadata remain for runtime and historical jobs.

## 8. Historical compatibility

- Job summaries and execution logs can still describe `visual_reference_attachments` and `reference_usage` from past runs.
- **Removed:** Live inventory URLs under `/api/v3/inventories/.../visual-references/...` — clients must use supplier reference image endpoints only.

## 9. Tests updated

| Area | Action |
| --- | --- |
| Backend | Removed legacy API/use-case/repo/resolver/domain/path tests; updated pipeline runner, job executor input resolution, error mapping, stored artifact access tests. |
| New | `test_migration_0029_drop_inventory_visual_references.py`, `test_inventory_visual_references_removed.py`, `test_reference_image_mime.py`. |
| Frontend | Full Vitest suite green after removals and test renames. |

## 10. Validation commands

Executed in this workspace:

```bash
cd backend
.venv/bin/python -m pytest tests/database/test_migration_0029_drop_inventory_visual_references.py \
  tests/api/test_inventory_visual_references_removed.py tests/api/test_error_mapping.py \
  tests/api/test_v3_stored_artifact_access_unit.py tests/application/utils/test_reference_image_mime.py \
  tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py \
  tests/infrastructure/pipeline/test_v3_job_executor_input_resolution.py -q --no-cov
# 115 passed

.venv/bin/python -m pytest tests/api/test_supplier_reference_images_api.py \
  tests/application/use_cases/test_upload_supplier_reference_images.py \
  tests/application/use_cases/test_manage_supplier_reference_images.py \
  tests/infrastructure/repositories/test_sql_supplier_reference_image_repository_unit.py \
  tests/application/services/test_supplier_reference_image_resolver.py \
  tests/application/services/test_aisle_analysis_context_builder.py \
  tests/pipeline/test_run_metadata.py -q --no-cov
# 78 passed (subset overlap with above)

.venv/bin/python -m pytest tests/infrastructure/pipeline/test_v3_job_executor_phase5.py -q --no-cov
# 21 passed

.venv/bin/ruff check src tests scripts
# All checks passed
```

```bash
cd frontend
npm run typecheck && npm run lint && npm run build
npm test -- --run
# 85 files, 493 tests passed
```

`scripts/db_migrate.py apply` was **not** run here (environment-specific); apply `0029` in a controlled SQL Server environment after backup.

## 11. Boundaries preserved

- Supplier reference API/UI unchanged in intent and still covered by tests.
- Active aisle processing remains supplier-reference-based (`SupplierReferenceImageResolver`).
- No storage objects deleted in C9.
- Prompt composition / LLM adapters were not modified for C9.

## 12. Observations/blockers

- Optional **C9.x / maintenance:** orphaned files under `v3_uploads/inventories/*/visual_references/*` were not scanned or deleted; approve a separate phase if physical cleanup is required.

## 13. Recommended next phase

**C10 — Phase C final closure** (documentation, communication to API consumers, production migration apply + verification checklist).
