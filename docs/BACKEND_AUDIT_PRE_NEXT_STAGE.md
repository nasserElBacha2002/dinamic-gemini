# Backend Audit — Pre-next-stage Review

**Dinamic Inventory v3.0**  
**Date:** 2025-03-06  
**Scope:** `src/domain`, `src/application`, `src/api`, `src/infrastructure`, `src/database/schema.sql`, worker/runtime, pipeline integration, and related backend tests.

---

## 1. Executive verdict

**READY WITH MINOR FIXES**

The backend respects the intended layering (api → application/use_cases → ports → infrastructure), domain is framework-agnostic, and the worker/runtime correctly uses shared v3 deps and the same application ports without depending on the HTTP layer. Persistence is parameterized and robust for the current stage; pipeline integration is explicit and auditable. A small set of fixes (duplicate dependency definition, one incorrect unit test) and documented limitations (non-atomic persist, v1 jobs legacy path) should be addressed before or immediately after moving to the next epic. No blocking architectural or safety issues were found.

---

## 2. What is correct

- **Architecture and dependency direction**
  - Routes are thin: v3 inventories route delegates to use cases and maps application exceptions to HTTP (404, 409, 422).
  - Use cases depend only on application ports (repositories, Clock, JobQueue, ArtifactStorage); no FastAPI or HTTP types.
  - Worker does not import API; it uses `runtime.v3_deps` and `infrastructure.pipeline.V3JobExecutor`; executor uses application `PersistAisleResultUseCase` and ports.
  - Dependency wiring lives in `api/dependencies.py` (FastAPI Depends) and `runtime/v3_deps.py` (neutral getters); infrastructure is injected, not imported by application.

- **Application layer**
  - Application exceptions are centralized in `application/errors.py` and used consistently (InventoryNotFoundError, AisleNotFoundError, ActiveJobExistsError, DuplicateAisleCodeError, PositionNotFoundError, UnsupportedAssetTypeError, EmptyUploadError).
  - Use cases are cohesive and scoped (e.g. GetInventory, CreateAisle, StartAisleProcessing, ListAislePositions, GetPositionDetail, PersistAisleResult).
  - Missing-resource and conflict scenarios raise these exceptions; routes map them to 404/409/422.

- **Persistence**
  - SQL repositories use parameterized queries throughout (no string interpolation of user input); invalid enum/JSON is handled with safe fallbacks and logging (e.g. position status → DETECTED, evidence type → POSITION_CROP, JSON parse → None + warning).
  - Repositories validate required fields on save (e.g. position/aisle created_at/updated_at); list methods document or implement filters (e.g. PositionRepository list_by_aisle with status, needs_review, min_confidence, sku_filter, pagination).
  - Schema is consistent with v3 domain: inventories, aisles, v3_jobs, source_assets, positions, product_records, evidences with sensible FKs and indexes.

- **Pipeline integration**
  - `V3JobExecutor` runs the hybrid pipeline, then calls `PersistAisleResultUseCase` with a command; no pipeline logic in routes.
  - `v3_report_mapper` uses explicit sentinels (SKU_UNKNOWN, EVIDENCE_PATH_NO_ARTIFACT) and audit flags in `detected_summary_json` for missing/invalid data; no silent fabrication of critical fields.
  - Traceability: job → aisle → source assets → pipeline output → persisted positions/product_records/evidences; evidence storage_path encodes job_id/run_id/relative path.

- **Observability**
  - Failures are logged (e.g. executor exception, persist re-raise, SQL JSON/decode warnings); non-atomic flows are documented (PersistAisleResult, UploadAisleAssets).

- **Tests**
  - Mapper and PersistAisleResult have meaningful unit tests (empty entities, one entity, needs_review, save ordering).
  - API wiring tests cover v3 inventories and aisles (create, list, get, 404/409/422, process, status, upload, list assets).
  - Repository tests exist for SQL inventory, aisle, source_asset and memory implementations.

---

## 3. Issues found

### Critical
- None.

### High
- **Duplicate `get_job_queue` in `api/dependencies.py`**  
  **What:** Two identical definitions of `get_job_queue()` (lines 63–66 and 68–71). The second overwrites the first.  
  **Why it matters:** Confusing for maintainers and static analysis; any change to the first is ignored.  
  **Recommendation:** Remove the duplicate; keep a single `get_job_queue()` that returns `V3JobQueueAdapter()`.

- **Non-atomic PersistAisleResult (known limitation)**  
  **What:** PersistAisleResultUseCase saves positions, then product_records, then evidences in sequence with no transaction. On failure it re-raises; earlier steps remain persisted.  
  **Why it matters:** Partial result data can remain (e.g. positions without evidences); job/aisle are still marked failed, but DB may need manual inspection or cleanup.  
  **Recommendation:** Document in runbook/ops; for next epic consider a single transaction or compensating cleanup when persist fails. Not blocking if accepted as current risk.

### Medium
- **v1 Jobs API bypasses application layer**  
  **What:** `api/routes/jobs.py` uses `database.repository` (JobsRepository, PalletResultsRepository, JobEventsRepository), `job_store`, and `job_store.create_job`/`get_job` directly. No use cases or v3 application ports for job create/status/result/artifacts.  
  **Why it matters:** Two parallel paths (v3 inventories/aisles/positions vs v1 jobs) increase maintenance and make it harder to evolve job lifecycle in one place.  
  **Recommendation:** Accept as intentional legacy slice for now; plan a later convergence (e.g. v3 job read/status via application layer) when moving to richer operational workflows.

- **GetInventory use case unit test expects wrong behavior**  
  **What:** `tests/application/use_cases/test_get_inventory.py::test_get_inventory_returns_none_when_not_found` calls `use_case.execute("nonexistent")` and asserts `result is None`. GetInventoryUseCase raises `InventoryNotFoundError` when not found, it does not return None.  
  **Why it matters:** Test is wrong; it would fail if run (or never actually exercises the “not found” path).  
  **Recommendation:** Change test to expect `InventoryNotFoundError` (e.g. `pytest.raises(InventoryNotFoundError)`).

### Low
- **Upload flow non-atomicity**  
  **What:** UploadAisleAssetsUseCase docstring states that partial state (files on disk without DB rows, or vice versa) can occur on failure; no automatic rollback.  
  **Why it matters:** Consistent with current design; acceptable if callers treat upload as best-effort on error.  
  **Recommendation:** Keep as-is; ensure runbook mentions possible partial uploads.

---

## 4. Architecture assessment

The backend structure remains appropriate and sustainable:

- **api:** FastAPI routes, schemas, and dependency injection only; no business logic.
- **application:** Use cases and ports (repositories, Clock, JobQueue, ArtifactStorage, contracts); no framework or infrastructure imports.
- **domain:** Entities and value types; no I/O or framework.
- **infrastructure:** SQL/memory repositories, queue/storage adapters, pipeline executor and report mapper; implements ports and may use application use cases (e.g. PersistAisleResult).
- **runtime:** Shared v3_deps used by both API (via Depends) and worker; single place for repo/clock selection and SQL vs in-memory fallback.

Worker execution is correctly separated from the API: the same `run_job` is used by the in-process worker thread started by the server; v3 jobs are handled by `V3JobExecutor` using application and infrastructure layers only. Pipeline integration is confined to infrastructure (executor + mapper); routes do not depend on pipeline or report format.

---

## 5. Persistence and pipeline integration assessment

- **Repositories:** SQL implementations validate required fields and use safe fallbacks for invalid DB data; list/query methods are honest about filters (position status, needs_review, sku_filter, pagination). Parameterized queries throughout; no SQL injection risk identified.
- **Result persistence:** Positions, product_records, and evidences are persisted in a defined order; failure is re-raised so the executor can mark job/aisle failed. Partial persistence is an accepted trade-off and documented.
- **Storage:** V3 artifact storage adapter is used for aisle uploads; path structure is predictable (e.g. aisles/{aisle_id}/raw/...). No assessment of disk quota or cleanup in this audit.
- **Pipeline integration:** Report-to-domain mapping is explicit and auditable; sentinels and `_audit` in detected_summary make missing/invalid data visible. Evidence paths and source_asset_id (currently None from mapper) are consistent with schema and domain.

Persistence and pipeline integration are safe and credible enough for continued development, with the known non-atomic persist and upload behaviors documented and acceptable for the current stage.

---

## 6. API / use-case assessment

- **Routes:** v3 inventories routes are thin: parse request, call use case, map domain to response, map application exceptions to HTTP. No business logic in route handlers.
- **Use cases:** Single responsibility and consistent error handling; commands/results are clear (e.g. CreateAisleCommand, ListAislePositionsCommand, PositionDetailResult).
- **Application errors:** Used consistently; API maps them to 404, 409, 422 as appropriate.
- **Contracts:** TypedDict/dataclass in `application/ports/contracts.py` (e.g. ProcessAislePayload, PositionListQuery) reduce reliance on raw dicts.

API and use-case design are coherent and maintainable. The only application-layer test issue found is the GetInventory “not found” test expecting None instead of an exception.

---

## 7. Test assessment

- **Strengths:** V3 report mapper and PersistAisleResult have focused unit tests; v3 inventories and aisles API wiring tests cover main flows and error paths (404, 409, 422); repository tests exist for SQL and memory.
- **Gaps:** One incorrect unit test (GetInventory not-found); no dedicated integration test for full v3 process_aisle run (worker + executor + persist) against a real or test DB; v1 jobs routes are not covered by the same use-case/port abstraction tests. For the current stage, coverage is sufficient provided the GetInventory test is fixed.

---

## 8. Readiness checklist

| Criterion | Yes/No | Justification |
|----------|--------|----------------|
| Backend architecture is stable enough | Yes | Layering and dependency direction are correct and consistent. |
| Use-case boundaries are clean enough | Yes | Single responsibility and port-based dependencies. |
| Persistence is safe enough | Yes | Parameterized SQL, validation, safe fallbacks, documented non-atomic flows. |
| Pipeline integration is credible enough | Yes | Explicit mapping, sentinels, audit fields, traceability. |
| API contracts are clear enough | Yes | Pydantic schemas and consistent error mapping. |
| Tests are sufficient for this stage | Yes* | *After fixing GetInventory not-found test. |
| No blocking issues remain | Yes | Duplicate get_job_queue and wrong test are minor fixes. |
| Safe to continue to next stage | Yes | With minor fixes applied and known limitations documented. |

---

## 9. Blocking fixes before next stage

1. **Remove duplicate `get_job_queue`** in `src/api/dependencies.py` (delete one of the two identical definitions).
2. **Fix GetInventory use case test** in `tests/application/use_cases/test_get_inventory.py`: for “not found”, expect `InventoryNotFoundError` instead of `result is None`.

---

## 10. Deferrable improvements

- Add an integration test that runs a v3 process_aisle job (executor + persist) against a test DB or in-memory repos to validate end-to-end persist and status updates.
- Document or add a runbook note for partial result data when PersistAisleResult fails (and optionally for partial uploads).
- Plan convergence of v1 job endpoints with the application layer when evolving job lifecycle (e.g. v3 job status/result via use cases).
- Consider a single transaction or compensating logic for PersistAisleResult when the next epic introduces more result flows or review workflows.

---

## 11. Final recommendation

**Proceed to the next stage** after applying the two blocking fixes (duplicate `get_job_queue`, GetInventory test). Treat non-atomic PersistAisleResult and upload as known, documented limitations. The backend is a credible base for richer result flows, review/manual correction, evidence/result visualization, and deeper operational workflows, with no blocking architectural or safety issues identified.
