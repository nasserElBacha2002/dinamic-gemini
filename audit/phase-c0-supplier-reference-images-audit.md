# C0 — Supplier Reference Images Full-Stack Audit

## 1. Executive summary

Recommended status: `READY_WITH_OBSERVATIONS`

Phase C can start with an additive supplier-level reference image module without breaking Phase A/B behavior, as long as:
- `inventory_visual_references` remains untouched and fully functional.
- Pipeline input resolution continues to read only inventory-level references in Phase C.
- New supplier endpoints reuse existing client/supplier ownership rules already established in Phase B.

Main observation: DB migration validation remains environment-blocked (`HYT00` SQL Server login timeout), so C1 should proceed with code/test-first plus explicit migration validation once DB connectivity is available.

## 2. Current legacy reference model

Legacy model today is inventory-oriented:
- Table: `inventory_visual_references`.
- Ownership: `inventory_visual_references.inventory_id -> inventories.id`.
- Contract is CRUD-like through inventory routes:
  - `GET /api/v3/inventories/{inventory_id}/visual-references`
  - `POST /api/v3/inventories/{inventory_id}/visual-references` (multipart file upload)
  - `PUT /api/v3/inventories/{inventory_id}/visual-references/{reference_id}` (replace file)
  - `DELETE /api/v3/inventories/{inventory_id}/visual-references/{reference_id}`
  - `GET /api/v3/inventories/{inventory_id}/visual-references/{reference_id}/file` (served file/signed URL)
- Domain model: `InventoryVisualReference` with legacy path fields plus provider-aware metadata.
- Pipeline consumes these references through inventory scope (`inventory_id`) via `AnalysisContext.visual_references`.

Legacy references are associated to inventory, not directly to aisle/job/source-asset. They are optional contextual inputs for analysis, not primary evidence.

## 3. Backend map

Primary backend files and responsibilities:

- `backend/src/database/schema.sql`
  - Canonical schema snapshot including `inventory_visual_references` table and provider metadata fields.
- `backend/src/database/migrations/versions/0002_add_merge_tables.sql`, `0003_add_merge_tables.sql`, `0004_add_merge_tables.sql`
  - Early creation of `inventory_visual_references`.
- `backend/src/database/migrations/versions/0005_add_storage_provider_metadata.sql`
  - Additive provider metadata columns (`storage_provider`, `storage_bucket`, `storage_key`, etc.).
- `backend/src/domain/inventory/visual_reference.py`
  - Domain entity and invariants.
- `backend/src/application/ports/repositories.py`
  - `InventoryVisualReferenceRepository` port contract.
- `backend/src/infrastructure/repositories/sql_inventory_visual_reference_repository.py`
  - SQL Server implementation.
- `backend/src/infrastructure/repositories/memory_inventory_visual_reference_repository.py`
  - In-memory implementation.
- `backend/src/application/use_cases/upload_inventory_visual_references.py`
  - Upload/list use cases, MIME validation, max count rule, best-effort rollback.
- `backend/src/application/use_cases/manage_inventory_visual_references.py`
  - Delete/replace use cases.
- `backend/src/api/routes/v3/inventories.py`
  - Inventory visual-reference API handlers and multipart parsing.
- `backend/src/api/dependencies.py`
  - Wiring for visual-reference use cases.
- `backend/src/api/services/v3_stored_artifact_access.py`
  - Provider-aware and legacy file serving logic (`s3` signed URL vs local fallback).
- `backend/src/application/services/inventory_visual_reference_resolver.py`
  - Maps repository rows to pipeline `VisualReferenceContext`.
- `backend/src/application/services/aisle_analysis_context_builder.py`
  - Injects inventory references into analysis context and instructions.
- `backend/src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py`
  - Resolves visual references to local temp files before provider execution.
- `backend/src/infrastructure/pipeline/input_artifact_resolver.py`
  - Provider-aware / legacy-local path resolution for source assets and visual references.

## 4. Frontend map

Primary frontend files and responsibilities:

- `frontend/src/api/inventoriesApi.ts`
  - Inventory visual-reference API client functions (`list/upload/delete/replace/fetch file`).
- `frontend/src/hooks/useInventories.ts`
  - Query hook `useInventoryVisualReferences`.
- `frontend/src/hooks/useMutations.ts`
  - Mutations for upload/delete/replace and invalidation strategy.
- `frontend/src/api/queryKeys.ts`
  - Cache key namespace `queryKeys.inventories.visualReferences(inventoryId)`.
- `frontend/src/features/inventories/components/InventoryReferenceImagesModule.tsx`
  - Orchestrates lazy load + mutations and drawer lifecycle.
- `frontend/src/components/ReferenceImagesDrawer.tsx`
  - Presentation wrapper on top of generic managed asset drawer.
- `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx`
  - Reusable upload/preview/replace/delete interaction shell.
- `frontend/src/pages/InventoryDetail.tsx`
  - Current UI entry point for legacy reference images.
- `frontend/src/pages/ClientDetail.tsx`
  - Existing client/supplier management screen and best placement candidate for supplier-level references.
- `frontend/src/api/clientSuppliersApi.ts`, `frontend/src/hooks/useClients.ts`
  - Existing client/supplier API and query patterns to reuse.
- `frontend/src/i18n/locales/es/translation.json`
  - Existing keys for reference drawer and supplier copy; some placeholders still English-like in current baseline.

## 5. Pipeline impact map

Current pipeline reference flow:
1. `V3JobExecutor` builds analysis context via `AisleAnalysisContextBuilder`.
2. `InventoryVisualReferenceResolver` reads references by `inventory_id`.
3. `V3ProcessAislePipelineRunner.resolve_visual_reference_paths()` downloads/copies each reference to local temp files.
4. `AnalysisContext.visual_references` is passed to providers/prompt composition and tracked in `reference_usage`.

What must NOT be touched in Phase C:
- `analysis_context` contract (`VisualReferenceContext`) for pipeline runtime.
- Existing resolver path from inventory references.
- Provider consumption logic and `reference_usage` metadata.
- Any prompt behavior that changes reference selection semantics.

Phase C must keep pipeline consuming inventory references only.

## 6. Storage/upload analysis

Current upload mechanism:
- `POST .../visual-references` uses multipart/form-data.
- API layer buffers upload to memory (`BytesIO`) and passes DTOs to use case.
- Use case writes via `ArtifactStorage` (`put_object` preferred, `save_file` fallback).
- DB persists both legacy (`storage_path`) and provider-aware metadata (`storage_*`, `content_type`, `etag`).
- Read path uses `resolve_visual_reference_file_response()`:
  - S3 => 307 signed URL redirect.
  - local => file response.
  - legacy rows => guarded local fallback (feature-flag controlled).

Recommendation for Phase C:
- Reuse existing artifact storage flow (same `ArtifactStorage` + provider metadata pattern).
- Keep multipart direct upload for supplier references (same as current visual-reference API).
- Avoid introducing a parallel bespoke artifact subsystem.

## 7. Recommended `supplier_reference_images` design

Recommended additive table:
- `id VARCHAR(36) PK`
- `client_supplier_id VARCHAR(36) NOT NULL FK -> client_suppliers(id)`
- `filename NVARCHAR(512) NOT NULL`
- `storage_path NVARCHAR(1024) NOT NULL` (legacy compatibility pattern)
- `storage_provider VARCHAR(16) NULL`
- `storage_bucket NVARCHAR(255) NULL`
- `storage_key NVARCHAR(1024) NULL`
- `content_type VARCHAR(128) NULL`
- `file_size_bytes BIGINT NULL`
- `etag NVARCHAR(128) NULL`
- `mime_type VARCHAR(128) NOT NULL`
- `file_size BIGINT NOT NULL`
- `label NVARCHAR(255) NULL` (optional, safe for Phase C)
- `description NVARCHAR(1024) NULL` (optional, safe for Phase C)
- `created_at DATETIME2 NOT NULL`
- `updated_at DATETIME2 NOT NULL` (recommended for future metadata edits)

Fields explicitly not recommended for C1:
- `deleted_at` (no soft-delete pattern today for visual references/source assets).
- `status` enum for images (no existing image status pattern; delete is hard delete).
- `sort_order` unless UI requires manual ordering in C2.
- `created_by` unless authenticated user identity is consistently persisted elsewhere.

Constraints/indexes:
- FK: `FK_supplier_reference_images_client_supplier`.
- Index: `IX_supplier_reference_images_client_supplier_id`.
- Optional unique constraint deferred (no clear uniqueness rule for filename/hash currently).

Naming conventions aligned with repo:
- Migration: `0028_supplier_reference_images.sql` (next sequential version).
- Domain model: `SupplierReferenceImage`.
- Port: `SupplierReferenceImageRepository`.
- SQL repo: `SqlSupplierReferenceImageRepository`.
- Memory repo: `MemorySupplierReferenceImageRepository`.
- Use cases:
  - `UploadSupplierReferenceImagesUseCase`
  - `ListSupplierReferenceImagesUseCase`
  - `DeleteSupplierReferenceImageUseCase`
  - optional `ReplaceSupplierReferenceImageUseCase` (if parity with inventory flow is desired).

## 8. Recommended API contract

Proposed endpoints fit current architecture and naming style:
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images`
- `DELETE /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}`
- optional parity endpoint:
  - `PUT /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}`
- optional file endpoint for preview:
  - `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file`

Path style is compatible with existing nested supplier routes under `/clients/{client_id}/suppliers`.

Validations (mandatory):
- `client_id` exists.
- `supplier_id` exists.
- `supplier.client_id == client_id`.
- `image_id` exists and belongs to `supplier_id`.
- cross-scope access blocked (client/supplier mismatch, image/supplier mismatch).

Error contract recommendation:
- Reuse `StructuredApiHttpError` + `reraise_if_mapped`.
- Add explicit codes/details in same catalog style as Phase B:
  - `SUPPLIER_REFERENCE_IMAGE_NOT_FOUND`
  - `CLIENT_SUPPLIER_CLIENT_MISMATCH` (already exists; reuse)
  - `CLIENT_NOT_FOUND` / `CLIENT_SUPPLIER_NOT_FOUND` (already exists; reuse)

Request/response shape:
- Keep response metadata aligned with `InventoryVisualReferenceResponse` to maximize frontend reuse.
- Do not expose internal storage path in response body.

## 9. Recommended frontend design

Preferred UI location:
- Extend `ClientDetail` with a supplier-focused section/module.
- No dedicated supplier detail page currently; client detail contains supplier management and is the natural host.

Suggested file structure (for later C2/C3):
- Types:
  - `frontend/src/api/types/responses.ts` add `SupplierReferenceImage`, list/upload responses.
  - `frontend/src/api/types/requests.ts` add optional metadata request type if label/description are supported.
- API:
  - `frontend/src/api/clientSuppliersApi.ts` add supplier reference images client methods.
  - `frontend/src/constants/v3ApiPaths.ts` add helper path builders for supplier references.
- Query keys:
  - `frontend/src/api/queryKeys.ts` add `queryKeys.clients.suppliers.referenceImages(...)`.
- Hooks:
  - `frontend/src/hooks/useClients.ts` add read hook.
  - `frontend/src/hooks/useMutations.ts` add upload/delete(/replace) mutations.
- Components:
  - `frontend/src/features/clients/components/SupplierReferenceImagesSection.tsx`
  - optionally `SupplierReferenceImagesModule.tsx` mirroring `InventoryReferenceImagesModule`.
  - reuse `ManagedImageAssetsDrawer` pattern.
- Tests:
  - `frontend/tests/SupplierReferenceImagesSection.test.tsx`
  - API hook/mutation tests and invalidation tests.
- i18n:
  - Add Spanish keys under `clients.suppliers.reference_images.*` (avoid hardcoded strings).

## 10. Legacy coexistence strategy

Mandatory coexistence rules:
- Keep `inventory_visual_references` table and endpoints unchanged.
- Keep pipeline reading inventory references only.
- Keep historical jobs/read APIs untouched.
- No `NOT NULL` retrofits on legacy image references.
- No physical file relocation in C1-C4.
- No automatic copy/migration of legacy references in core C phases.

Should Phase C include real migration/copy of legacy references?
- Recommendation: **No** for initial C1-C5.
- If needed, defer to C6 as read-only/dry-run analysis script producing a report (counts, conflicts, estimated copy plan) without mutating DB/files.

## 11. Risks and mitigations

1) API scope leakage risk (cross-client image access)
- Mitigation: enforce `client -> supplier -> image` ownership chain in use cases and tests.

2) Storage logic duplication risk
- Mitigation: reuse existing artifact storage adapter pattern and file-serving service.

3) Legacy pipeline regression risk
- Mitigation: do not wire supplier references into `AnalysisContext` in Phase C.

4) Frontend contract drift risk
- Mitigation: keep response shape parallel to inventory references and follow existing React Query invalidation patterns.

5) Migration/environment validation risk
- Mitigation: keep migration additive; validate in CI/connected env once SQL connectivity is available.

6) i18n quality risk
- Mitigation: add Spanish keys from start; avoid placeholder English strings.

## 12. Proposed implementation slices

- C1 — Backend supplier_reference_images foundation
  - New table + domain + ports + repos + basic use cases + dependency wiring.
- C2 — Backend API contract and validations
  - New nested supplier image routes with ownership/error mapping + API/use case tests.
- C3 — Frontend supplier reference images UI (minimal management)
  - List/upload/delete UI in `ClientDetail` supplier context with Spanish i18n.
- C4 — Legacy coexistence hardening
  - Regression tests proving legacy inventory references and pipeline unchanged.
- C5 — Documentation and rollout guardrails
  - Update docs/runbooks and explicit “Phase E pipeline switch” boundary.
- C6 — Optional dry-run legacy copy analysis
  - Read-only script/report for potential legacy-to-supplier mapping feasibility.
- C7 — Phase C closure audit
  - Verify contracts, tests, and coexistence before Phase E planning.

## 13. Commands executed

Backend:
- `rg`/file mapping across `backend/src`, `backend/tests`, `backend/src/database/migrations`.
- `.venv/bin/python -m pytest --collect-only` ✅ (1945 tests collected).
- `backend/scripts/db_migrate.py status` ❌ `HYT00` login timeout.
- `backend/scripts/db_migrate.py validate` ❌ `HYT00` login timeout.

Frontend:
- `rg`/file mapping across `frontend/src`, `frontend/tests`.
- `npm test -- --run` ✅ (81 files, 495 tests passed).
- `npm run typecheck`, `npm run lint`, `npm run build` could not be executed reliably in this environment due script resolution inconsistencies from command runner context; no code changes were made.

## 14. Open questions

Only blocking or near-blocking:

1. Should supplier reference images support `PUT` replace in C2 (full parity) or postpone to a later slice?
2. Should `label/description` be included in C1 schema or deferred until UI metadata editing is requested?
3. Is Phase C expected to cap images per supplier (like inventory’s max=3) and if yes, should it be config-driven from day one?

## 15. Technical questions (explicit answers)

1) Current structure of `inventory_visual_references`?
- Inventory-owned image metadata with legacy path + provider metadata, no soft-delete/status.

2) Which endpoints create/list/delete references?
- Inventory endpoints under `/api/v3/inventories/{inventory_id}/visual-references` (+ replace and file fetch).

3) Legacy association target?
- Inventory-level association only.

4) File storage model?
- Reusable artifact storage abstraction (`ArtifactStorage` / `ArtifactStore`) with local/S3 support.

5) Upload style?
- Multipart/form-data direct upload.

6) Best implementation pattern to reuse?
- `upload_inventory_visual_references.py` + `manage_inventory_visual_references.py` + inventory route/dependency wiring pattern.

7) Where should new module live?
- Backend: parallel to inventory visual reference modules (`domain`, `application/use_cases`, `infrastructure/repositories`, `api/routes/v3/clients.py` extension or dedicated submodule).

8) Direct upload or artifact reuse?
- Reuse artifact storage (same multipart entry, same storage adapter path).

9) Existing ownership validations for `client_supplier_id`?
- `CreateAisleUseCase` validates supplier existence, inventory client requirement, and client match.

10) Where to reuse client+supplier validation?
- Reuse/get inspiration from `CreateAisleUseCase` and supplier retrieval use cases in clients module.

11) Existing soft-delete pattern?
- No general soft-delete pattern found for related entities.

12) Existing status pattern for similar entities?
- Clients/suppliers use `active/inactive`; image references currently do not.

13) Current tests covering visual references?
- Backend API/use case/repository tests around inventory visual references; frontend drawer and inventory detail tests.

14) New tests needed in C1/C2?
- Repository unit/integration tests for supplier references.
- Use case tests for ownership, upload constraints, delete behavior.
- API wiring tests for route contract and structured errors.

15) Frontend screen to extend?
- `ClientDetail` (supplier section).

16) Real supplier detail page?
- No dedicated supplier detail page currently; supplier view is nested in client detail.

17) Existing frontend hook patterns to reuse?
- `useInventoryVisualReferences` + mutation hooks and `queryKeys` patterns; `useClientSuppliers` for scoping.

18) Risks breaking legacy inventories/aisles?
- High if pipeline/source resolver is touched; avoid by isolating Phase C to new supplier module only.

19) Risks duplicating storage/upload logic?
- Medium-high; mitigate by reusing artifact abstractions and drawer/module UI pattern.

20) What is out of scope for Phase C?
- Pipeline consumption switch to supplier references, destructive migration, legacy table removal, mandatory backfill/copy.

