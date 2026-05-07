# C4 — Legacy Reference Dependency Audit

## 1. Executive summary

**Status:** **READY_FOR_C5** (with **observations** — supplier mapping rules for migrated rows must be explicit before C6).

This audit maps dependencies on the **inventory-scoped** visual reference system (`inventory_visual_references`, inventory API routes, resolver/builder/runner paths, UI, tests, and persisted job metadata). The **supplier-scoped** system (`supplier_reference_images`) is live for API/UI but **not** wired into the aisle processing pipeline.

**Product decision (confirmed):** The legacy inventory visual reference system must **not** remain indefinitely. Planned progression: temporary coexistence → migration → pipeline switch → write-disable/UI sunset → removal → closure (`C5`–`C10`).

**No runtime, schema, data, pipeline, or prompt changes were made during C4.** Deliverables are documentation and read-only search artifacts only.

---

## 2. Product decision

| Decision | Detail |
|----------|--------|
| End state | Remove deprecated inventory-level reference images after safe migration and pipeline activation on supplier references. |
| Coexistence | **Temporary only** — operational clarity requires a bounded transition, not permanent dual sources of truth. |
| Out of scope for C4 | Migration execution, pipeline edits, disabling endpoints, UI removal, data copy/delete. |

---

## 3. Backend dependency map

**Discovery artifact:** full path list in `audit/raw/phase-c4-backend-legacy-reference-files.txt` (66 files from ripgrep).

### 3.1 Representative classifications

| Area | File / module | Responsibility | Class tag | Notes / future action |
|------|---------------|----------------|-----------|------------------------|
| DB | `backend/src/database/migrations/versions/0002_add_merge_tables.sql`, `0003_*`, `0005_add_storage_provider_metadata.sql`, `schema.sql` | Table `inventory_visual_references` + provider columns | **G** (after migration) / **I** until strategy | Keep until cutover + archival strategy defined |
| Domain | `backend/src/domain/inventory/visual_reference.py` | `InventoryVisualReference` entity | **G** / **I** | |
| Ports | `backend/src/application/ports/repositories.py` | `InventoryVisualReferenceRepository` ABC | **H** until pipeline switch | Also wired in worker DI |
| Use cases | `upload_inventory_visual_references.py`, `manage_inventory_visual_references.py` | CRUD + storage writes | **A**, **G** | Supplier upload **reuses** `_normalize_mime` / `ALLOWED_MIME_TYPES` — **D** coupling |
| Services | `inventory_visual_reference_resolver.py` | `list_by_inventory` → `VisualReferenceContext` | **C**, **H** | Inventory-only scope |
| Services | `aisle_analysis_context_builder.py` | Builds `AnalysisContext` using resolver | **C**, **H** | Uses inventory_id only |
| Services | `inventory_visual_reference_lookup.py` | Select ref by id (API file route helper) | **A**, **B** | |
| Pipeline runner | `v3_process_aisle_pipeline_runner.py` | Second `list_by_inventory`; `resolve_visual_reference_paths` | **C**, **H** | **Critical dependency** |
| Resolver worker | `input_artifact_resolver.py::resolve_visual_reference` | Download/copy reference blobs | **C**, **B** | Typed on **`InventoryVisualReference`** — supplier switch needs generalization (**I**) |
| Executor | `v3_job_executor.py` | Wires repos + failure metadata for resolution errors | **C**, **F** | Writes `visual_reference_context` on resolution failure |
| Job worker | `backend/src/jobs/worker.py` | Supplies `inventory_visual_reference_repo` to executor | **C**, **H** | |
| Container | `runtime/app_container.py` | Repository singleton | **A**, **H** | |
| API | `api/routes/v3/inventories.py` | POST/GET/PUT/DELETE/file | **A**, **B** | See §8 |
| API access | `api/services/v3_stored_artifact_access.py` | `resolve_visual_reference_file_response` | **B**, **D** | `resolve_supplier_reference_image_file_response` delegates here |
| Schemas | `api/schemas/inventory_schemas.py` | Response models | **A** | |
| Errors | `api/errors/error_mapping.py` | Structured errors for refs | **A** | |
| Dependencies | `api/dependencies.py` | Use case factories | **A** | |
| Pipeline prep | `pipeline/services/analysis_visual_reference_prep.py` | Gemini attachments from `analysis_context.visual_references` | **C**, **H** | |
| Pipeline adapter | `pipeline/adapters/hybrid_global_analysis_strategy.py` | Provider metadata flags for refs consumed | **C**, **H** | |
| Metadata | `pipeline/run_metadata.py` | `visual_reference_context` block | **C**, **F** | Drives `reference_usage` in API |
| API summaries | `api/routes/v3/shared.py` + `reference_usage_from_job_result.py` | Parse persisted usage | **F** | Historical jobs depend on JSON shape |
| LLM docs | `llm/prompt_composer/hybrid_profiles.py` | Text: “Inventory visual references…” | **H** / prompt phase | Update when switching semantics (not C4) |
| Contracts | `pipeline/contracts/analysis_context.py` | `VisualReferenceContext.role` default `inventory_reference` | **C**, **I** | Naming/docs imply inventory-only |
| Cleanup script | `database/sqlserver_business_data_cleanup.py` | References table for wipe ordering | **I** | Operational tooling |
| Supplier paths | `application/utils/supplier_reference_image_paths.py` | Imports `extension_from_mime_type` from inventory paths util | **D** | Shared helper — keep generic portion |

**Legend (requested buckets):**  
**A** Legacy CRUD/API · **B** Legacy storage/file serving · **C** Pipeline runtime · **D** Shared with supplier images · **E** Test-only · **F** Historical/job readout · **G** Removable after migration · **H** Must remain until pipeline switch · **I** Must remain until compatibility/archival strategy defined  

---

## 4. Frontend dependency map

**Discovery artifact:** `audit/raw/phase-c4-frontend-legacy-reference-files.txt` (24 files).

| File | Role | Class | Notes |
|------|------|-------|-------|
| `pages/InventoryDetail.tsx` | Embeds `InventoryReferenceImagesModule` | **A** | Visible alongside rest of inventory UX; supplier UI is on **ClientDetail** (separate surface after C3). |
| `features/inventories/components/InventoryReferenceImagesModule.tsx` | Queries + mutations + `ReferenceImagesDrawer` | **A**, **D** (hooks) | Primary legacy UI entry |
| `components/ReferenceImagesDrawer.tsx` | Inventory drawer wrapper | **A** | Uses `ManagedImageAssetsDrawer` |
| `features/imageAssets/hooks/useInventoryReferencePreview.ts` | Blob preview fetch | **C** (API), **D** | Calls `fetchInventoryVisualReferenceFile` |
| `api/inventoriesApi.ts` | list/upload/delete/replace/file fetch | **C** | |
| `api/client.ts` | Barrel exports | **C** | |
| `api/queryKeys.ts` | `inventories.visualReferences(inventoryId)` | **D** | |
| `hooks/useInventories.ts` | `useInventoryVisualReferences` | **D** | |
| `hooks/useMutations.ts` | upload/delete/replace mutations | **E** | |
| `hooks/index.ts` | Exports | **D** | |
| `api/types/responses.ts` | `InventoryVisualReference`, job `reference_usage` | **C**, **F** | |
| `features/inventories/components/InventoryAislesSection.tsx` | Column “reference usage” | **F** | Consumes `reference_usage` on runs |
| `features/inventories/adapters/referenceUsageViewModel.ts` | Maps `reference_usage` for UI | **F** | |
| `components/ExecutionLogPanel.tsx` | `visual_reference_attachments`, counts | **F** | Historical/debug viewing |
| `components/imageAssets/ManagedImageAssetsDrawer.tsx` | Generic drawer chrome | **F** (shared) | **NOT legacy-only** — also used by **supplier** drawer (**G** keep). |
| `i18n/.../translation.json` | `aisle.reference_usage`, inventory reference drawer keys | **H** / cleanup later | |
| `features/inventories/hooks/useCreateInventoryFlow.ts` | Optional upload after create | **A**, **E** | |

---

## 5. Pipeline dependency map (detailed Q&A)

**Flow diagram (text):** see `audit/raw/phase-c4-pipeline-legacy-reference-flow.txt`.

| # | Question | Answer |
|---|----------|--------|
| 1 | Where does the pipeline load inventory visual references? | `InventoryVisualReferenceResolver.resolve_for_inventory` and again in `V3ProcessAislePipelineRunner.build_pipeline_input` via `list_by_inventory`. Resolution to temp files: `WorkerInputArtifactResolver.resolve_visual_reference`. |
| 2 | Scope: inventory, aisle, job? | **Per `inventory_id` only** (from `aisle.inventory_id`). **Not** scoped by `aisle_id` or `job_id`. |
| 3 | Does it know `client_supplier_id`? | **No.** `Aisle.client_supplier_id` exists in domain/DB but is **not** used in reference loading today. |
| 4 | What must change for supplier images? | New resolver path (e.g. load by `aisle.client_supplier_id` or explicit job parameters), repository port for `SupplierReferenceImage`, and **generalize** `resolve_visual_reference` (currently assumes `InventoryVisualReference` rows). Likely dual-read/feature flag during transition. |
| 5 | Persisted metadata about refs used? | `result_json.visual_reference_context` (`run_metadata.RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT`): resolved flags, counts, `reference_ids`, optional `resolution_error`. API exposes subset as `reference_usage` (`reference_usage_schemas.py`). Execution log / Gemini payload may list `visual_reference_attachments`. |
| 6 | Break historical job detail if table removed? | **Yes, if** UI or tooling tries to re-fetch **live** rows or files by legacy id without migration/archival. **No, if** job JSON + blobs remain sufficient for read-only auditing **or** ids map cleanly to new supplier rows/files. |
| 7 | Break old job artifacts? | Binary artifacts under job dirs reference resolved temp paths at run time; durable artifacts/logs reference logical ids and filenames. **Physical legacy blobs** remain in storage until deleted — removal of **DB rows** without migrating storage breaks `/file` serving for those ids. |
| 8 | Readable historical jobs if table dropped? | Partially: JSON summaries remain; **interactive** “open reference” degrades unless migrated or archived copies exist. |
| 9 | Denormalize `reference_usage` before removal? | **Recommended** for long-term read-only UX: snapshot supplier ids + filenames + storage keys into immutable job metadata **or** retain a slim archival mapping table until retention policy expires. |
|10 | Minimum safe pipeline switch plan? | (1) Implement supplier resolution behind flag. (2) Shadow/dual-read validation on staging. (3) Enable supplier path per environment. (4) Monitor `visual_reference_context` + attachment errors. (5) Freeze legacy writes (C8). (6) Migrate remaining blobs (C6). (7) Remove legacy code paths (C9). |

---

## 6. Database / data dependency map

**Table:** `inventory_visual_references` (see migrations `0002`/`0003`, columns extended in `0005` for provider metadata).

**Related modeling for migration analytics:**

- `inventories.client_id` — nullable (`0026`): inventories may lack client linkage → supplier target ambiguous.
- `aisles.client_supplier_id` — nullable (`0027`): aisle may lack supplier → pipeline cannot infer supplier from aisle alone today.
- `supplier_reference_images` — target store (`0028`); paths like `client_suppliers/{id}/reference_images/...` (`supplier_reference_image_paths.py`).

**Dry-run SQL plan (do not execute destructively here):** `audit/raw/phase-c4-sql-dry-run-plan.sql`.

**Mapping risk:** One inventory can have **multiple** `client_supplier_id` values across aisles → **no deterministic** “inventory → single supplier” mapping for legacy refs without a **product rule** (e.g. default supplier per inventory, manual mapping UI, or duplicate ref copies per supplier).

---

## 7. Shared storage / file serving map

| Component | Inventory-specific? | Generic / reused? |
|-----------|--------------------|-------------------|
| `inventory_visual_reference_paths.py` | Path layout `inventories/{id}/visual_references/...` | **`extension_from_mime_type`** reused by supplier paths (**D**) |
| `supplier_reference_image_paths.py` | Supplier layout | Uses shared MIME extension helper (**D**) |
| `v3_stored_artifact_access.resolve_visual_reference_file_response` | Docstring mentions inventory row | **Actually duck-typed**: works for any object with `storage_provider`, `storage_key`, `storage_bucket`, `storage_path`, `filename`, `mime_type`. **Supplier wrapper calls same function.** |
| `input_artifact_resolver.resolve_visual_reference` | Uses **`InventoryVisualReference`** domain type | **Must evolve** for supplier rows or a protocol (**I**) |
| Worker download logic | Same patterns as source assets | Keep generic download/copy helpers |

**Recommendation:** Do **not** delete `resolve_visual_reference_file_response` during cleanup; consider renaming to `resolve_stored_reference_image_response` in a later refactor once inventory-specific callers are gone.

---

## 8. Legacy endpoint map

See `audit/raw/phase-c4-legacy-endpoints-map.txt` for the tabulated list.

**Summary recommendation:**  
- **Writes** (POST/PUT/DELETE): **B** disable first in production once supplier workflow + pipeline are authoritative (**C8**).  
- **Reads/list/file**: **A** keep temporarily; **C** consider read-only period for historical incidents; **D** remove when DB + storage no longer serve legacy ids (**C9**).

---

## 9. Test dependency map

### Backend (representative)

| Test module | Dependency |
|-------------|------------|
| `backend/tests/api/test_inventory_visual_references_api.py` | Legacy REST contracts |
| `backend/tests/application/use_cases/test_upload_inventory_visual_references.py` | Upload rules, storage paths, rollback |
| `backend/tests/application/use_cases/test_manage_inventory_visual_references.py` | Delete/replace |
| `backend/tests/infrastructure/repositories/test_sql_inventory_visual_reference_repository_unit.py` | SQL mapping |
| `backend/tests/infrastructure/repositories/test_memory_inventory_visual_reference_repository.py` | Memory store |
| `backend/tests/application/services/test_inventory_visual_reference_resolver.py` | Resolver |
| `backend/tests/application/services/test_aisle_analysis_context_builder.py` | AnalysisContext assembly |
| `backend/tests/infrastructure/pipeline/test_v3_job_executor_*.py`, `test_v3_job_executor_input_resolution.py` | Pipeline input + refs |
| `backend/tests/pipeline/test_run_metadata.py` | `visual_reference_context` |
| `backend/tests/domain/test_inventory_visual_reference_entity.py` | Entity validation |
| `backend/tests/infrastructure/storage/test_inventory_visual_reference_paths.py` | Path helpers |
| `backend/tests/api/test_error_mapping.py` | Mapped errors |

**Later:** Replace or narrow tests when endpoints are disabled; keep regression tests for **metadata parsing** (`reference_usage`) if JSON schema stays stable.

### Frontend

| Test module | Dependency |
|-------------|------------|
| `frontend/tests/ReferenceImagesDrawer.test.tsx` | Legacy drawer |
| `frontend/tests/InventoryDetailPage.test.tsx` | Mocks inventory visual ref hooks heavily |
| `frontend/tests/CreateInventoryDialog.visualReferences.test.tsx` | Create flow upload |
| `frontend/tests/ExecutionLogPanel.test.tsx` | `visual_reference_*` log payload |

**Later:** Remove or rewrite when legacy UI removed; keep execution log tests if shape remains for historical logs.

---

## 10. Removal risk analysis

| Risk | Mitigation |
|------|------------|
| Pipeline silently loses references | Feature-flagged dual-read + staging parity checks on `visual_reference_context`. |
| Wrong supplier mapping | Explicit migration rules; reports for multi-supplier inventories (SQL plan §6). |
| Broken `/file` URLs after DB drop | Migrate blobs + preserve id mapping or archive static payloads in job metadata. |
| Operator confusion (two UIs) | Time-bound coexistence; comms; hide inventory drawer in **C8** once stable. |
| Historical audits | Retain JSON + durable artifacts; optional denormalized summary fields. |
| Over-deletion of shared helpers | Preserve `resolve_visual_reference_file_response` and generic artifact download paths used by supplier (**§7**). |

---

## 11. Future migration / removal roadmap (C5–C10)

### C5 — Legacy reference migration **dry-run**

| | |
|--|--|
| **Objective** | Validate data volumes, mapping eligibility, and failure modes without writes to supplier tables (or use transactional rollback sandboxes). |
| **Scope** | Execute read-only SQL (`audit/raw/phase-c4-sql-dry-run-plan.sql` expanded); prototype mapping reports; document ambiguous inventories. |
| **Out of scope** | Production writes, pipeline changes. |
| **Files likely affected** | `audit/raw/*`, optional `scripts/` read-only analyzers. |
| **Tests** | None required for dry-run scripts; optional snapshot tests for mapping pure functions if introduced. |
| **Acceptance criteria** | Signed-off mapping rules; inventory/supplier edge cases enumerated; rollback N/A (read-only). |
| **Rollback** | N/A |

### C6 — Real migration / copy to `supplier_reference_images`

| | |
|--|--|
| **Objective** | Copy legacy blobs + insert supplier rows with deterministic ids + mapping table for traceability. |
| **Scope** | Backend migration job/script; storage copy or pointer reuse per strategy; audit logging. |
| **Out of scope** | Pipeline switch; disabling legacy API. |
| **Files likely affected** | New use case/module under `application/use_cases`, infra storage, migrations for mapping table if needed. |
| **Tests** | Integration tests with temp DB + fake storage; idempotency tests. |
| **Acceptance criteria** | All targeted legacy refs reachable via supplier API/file endpoints; mapping auditable. |
| **Rollback** | Restore DB backup; delete migrated supplier rows if segregated batch. |

### C7 — Pipeline switch to supplier references

| | |
|--|--|
| **Objective** | Load references from supplier repository keyed by operational rules (`aisle.client_supplier_id` + fallbacks TBD). |
| **Scope** | `AisleAnalysisContextBuilder`, `V3ProcessAislePipelineRunner`, `input_artifact_resolver`, ports, worker wiring; feature flag. |
| **Out of scope** | Removing legacy table/endpoints. |
| **Files likely affected** | Files listed in §3 pipeline rows + tests under `infrastructure/pipeline`. |
| **Tests** | Resolver unit tests; executor integration tests; attachment prep tests. |
| **Acceptance criteria** | Jobs produce correct `visual_reference_context` using supplier ids; no regression on aisles without supplier if product defines behavior. |
| **Rollback** | Disable flag; revert deployment. |

### C8 — Disable legacy writes + hide old UI

| | |
|--|--|
| **Objective** | Stop mutating inventory-level refs in prod; reduce accidental divergence. |
| **Scope** | API 405/403 for POST/PUT/DELETE; UI hide or read-only mode; optional admin override flag. |
| **Out of scope** | DB drop. |
| **Files likely affected** | `inventories.py`, `InventoryReferenceImagesModule.tsx`, mutations hooks. |
| **Tests** | API tests expect disabled verbs; frontend tests updated. |
| **Acceptance criteria** | No successful legacy uploads in prod metrics; supplier path remains viable. |
| **Rollback** | Re-enable routes via flag. |

### C9 — Remove legacy inventory reference system

| | |
|--|--|
| **Objective** | Delete dead code paths after retention window; drop table when safe. |
| **Scope** | Remove use cases, repos, routes, UI, hooks; DB migration to drop `inventory_visual_references` **only** after archival policy satisfied. |
| **Out of scope** | Changing Gemini prompt contracts unless separately approved. |
| **Files likely affected** | Most paths listed in raw ripgrep outputs; shrink `input_artifact_resolver` signature if generalized earlier. |
| **Tests** | Delete obsolete tests; ensure supplier + metadata tests remain green. |
| **Acceptance criteria** | Repo grep clean for inventory visual refs; CI green; DB migrated in controlled window. |
| **Rollback** | Restore from backup / redeploy previous artifact (last resort). |

### C10 — Phase C closure

| | |
|--|--|
| **Objective** | Documentation, runbooks, retention confirmation, stakeholder sign-off. |
| **Scope** | Update product docs, operator guides, changelog. |
| **Acceptance criteria** | Single canonical reference-image story (supplier-scoped) documented; legacy mentions archived. |

---

## 12. Commands executed

Listed in `audit/raw/phase-c4-command-results.txt`.

---

## 13. Open questions

**Non-blocking for C5 kickoff (engineering may proceed with analytics):**

1. **Supplier assignment rule** when `aisles.client_supplier_id` is null or mixed across an inventory — duplicate images vs force operator assignment?
2. **Retention window** for legacy rows/files after C6 (legal/ops).
3. Whether **prompt copy** should say “supplier references” vs “inventory references” after switch (**C7**+, not C4).

**Blocking before C6 execution:**

- Signed **mapping specification** for ambiguous inventories (multi-supplier, missing `client_id`).

---

## 14. Final recommendation

**READY_FOR_C5** — Dependency surface is sufficiently mapped to begin quantified dry-run analysis and mapping design. **READY_WITH_RISKS** if product refuses to decide supplier-mapping rules before C5; the technical audit itself is complete.

**Generated artifacts**

- `audit/phase-c4-legacy-reference-dependency-audit.md` (this file)
- `audit/raw/phase-c4-backend-legacy-reference-files.txt`
- `audit/raw/phase-c4-frontend-legacy-reference-files.txt`
- `audit/raw/phase-c4-pipeline-legacy-reference-flow.txt`
- `audit/raw/phase-c4-legacy-endpoints-map.txt`
- `audit/raw/phase-c4-sql-dry-run-plan.sql`
- `audit/raw/phase-c4-command-results.txt`
