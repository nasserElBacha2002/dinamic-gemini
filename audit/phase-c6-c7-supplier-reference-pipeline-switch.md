# C6/C7 — Supplier Reference Pipeline Switch

## 1. Executive summary

**Status:** **READY_FOR_C8**

- **C6:** Migration confirmed **NO_OP** — C5.1 strict dry-run showed zero legacy `inventory_visual_references` rows; no copy, insert, delete, or storage moves were performed for migration purposes.
- **C7:** Active v3 aisle processing now resolves visual references from **`supplier_reference_images`** using **`aisles.client_supplier_id`**. The pipeline no longer calls **`inventory_visual_reference_repo.list_by_inventory`** for job execution. Legacy inventory reference **API and table remain** for C8/C9 retirement.

---

## 2. C6 no-op migration confirmation

Verified **`audit/raw/phase-c5-legacy-reference-migration-summary.json`** at phase completion:

| Field | Value |
|--------|--------|
| `require_db_mode` | `true` |
| `db_connected` | `true` |
| `total_legacy_reference_rows` | `0` |
| `auto_mappable_rows` | `0` |
| `ambiguous_rows` | `0` |
| `missing_storage_rows` | `0` |

**C6 status:** **NO_OP_CONFIRMED** — no migration rows to copy, no storage objects to copy for migration, no inserts into `supplier_reference_images` required for legacy migration, no deletes from `inventory_visual_references`.

---

## 3. Scope implemented

- New **`SupplierReferenceImageResolver`** → **`VisualReferenceContext`** with **`role="supplier_reference"`**.
- **`AisleAnalysisContextBuilder`** builds context from **`aisle.client_supplier_id`** (empty list when null).
- **`V3ProcessAislePipelineRunner`** loads artifact rows via **`SupplierReferenceImageRepository.list_by_supplier`** (no inventory-scoped listing for active jobs).
- **`WorkerInputArtifactResolver.resolve_visual_reference`** accepts a **`ReferenceImageRecord`** protocol (inventory or supplier rows).
- **`build_visual_reference_context`** optionally adds **`reference_source": "supplier_reference_images"`** when any reference uses **`supplier_reference`** role (additive; parsers that ignore unknown keys stay safe).

---

## 4. Files changed (responsibilities)

| Area | Files |
|------|--------|
| Resolver | `backend/src/application/services/supplier_reference_image_resolver.py` (new) |
| Builder | `backend/src/application/services/aisle_analysis_context_builder.py` |
| Artifact resolution | `backend/src/infrastructure/pipeline/input_artifact_resolver.py` (`ReferenceImageRecord`) |
| Runner | `backend/src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py` |
| Executor | `backend/src/infrastructure/pipeline/v3_job_executor.py` |
| Worker wiring | `backend/src/jobs/worker.py` |
| Metadata | `backend/src/pipeline/run_metadata.py` |
| Contracts | `backend/src/pipeline/contracts/analysis_context.py` (role documentation) |
| Tests | `backend/tests/application/services/test_supplier_reference_image_resolver.py` (new), `test_aisle_analysis_context_builder.py`, pipeline/executor tests, `test_run_metadata.py` |
| Report | `audit/phase-c6-c7-supplier-reference-pipeline-switch.md` (this file) |

---

## 5. New runtime reference resolution

1. Load **`Aisle`** for the job → read **`client_supplier_id`**.
2. If set: **`SupplierReferenceImageResolver.resolve_for_supplier`** → **`AnalysisContext.visual_references`** (ordered like repo: `created_at`, `id`).
3. **`build_pipeline_input`** loads the same supplier rows into **`references_by_id`** for **`resolve_visual_reference_paths`** / **`WorkerInputArtifactResolver`**.

---

## 6. Missing supplier / no images behavior

- **`client_supplier_id` null:** no supplier refs loaded; processing continues with **zero** visual references.
- **Supplier set but zero images:** **zero** references; **no fallback** to `inventory_visual_references`.

---

## 7. Artifact resolution changes

- **`ReferenceImageRecord`** protocol: `id`, `storage_path`, `storage_provider`, `storage_bucket`, `storage_key`, `filename`, `mime_type`.
- **`SupplierReferenceImage`** and **`InventoryVisualReference`** both satisfy it structurally.

---

## 8. Metadata / reference_usage behavior

- Existing **`visual_reference_context`** keys unchanged (**`resolved`**, **`reference_ids`**, **`resolved_count`**, **`provider_consumed`**, **`provider_consumed_count`**).
- Optional additive **`reference_source`** when supplier-role references are present.
- **`reference_usage_from_job_result`** unchanged (uses known keys only).

---

## 9. Legacy compatibility

- **`inventory_visual_references`** table **not** dropped.
- Legacy inventory visual reference **HTTP API** unchanged (still wired via **`get_inventory_visual_reference_repo()`**).
- **`inventory_reference`** role remains valid for historical **`analysis_context`** payloads.

---

## 10. Tests added/updated

- **New:** `test_supplier_reference_image_resolver.py` — mapping, empty supplier, blank id.
- **Updated:** `test_aisle_analysis_context_builder.py` — supplier vs no supplier vs instructions.
- **Updated:** `test_v3_process_aisle_pipeline_runner.py`, `test_v3_job_executor_input_resolution.py`, `test_v3_job_executor_phase5.py`, `test_v3_job_executor_coordination.py`, `test_v3_job_executor_analysis_context.py` (skipped smoke paths aligned).
- **Updated:** `test_run_metadata.py` — **`reference_source`** when **`supplier_reference`** role.

---

## 11. Validation commands

Run from **`backend/`** (examples):

```bash
python3 -m pytest tests/application/services/test_supplier_reference_image_resolver.py -q --no-cov
python3 -m pytest tests/application/services/test_aisle_analysis_context_builder.py -q --no-cov
python3 -m pytest tests/infrastructure/pipeline/test_v3_job_executor_input_resolution.py -q --no-cov
python3 -m pytest tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py -q --no-cov
python3 -m pytest tests/infrastructure/pipeline/test_v3_job_executor_phase5.py -q --no-cov
python3 -m pytest tests/pipeline/test_run_metadata.py -q --no-cov
python3 -m pytest tests/api/test_inventory_visual_references_api.py tests/application/use_cases/test_upload_inventory_visual_references.py tests/application/use_cases/test_manage_inventory_visual_references.py -q --no-cov
python3 -m pytest tests/api/test_supplier_reference_images_api.py tests/application/use_cases/test_upload_supplier_reference_images.py tests/application/use_cases/test_manage_supplier_reference_images.py -q --no-cov
python3 -m ruff check src tests scripts
```

*(Exact command results recorded at merge time in CI / local runs.)*

---

## 12. Boundaries preserved

- Frontend unchanged for this phase (per plan).
- Prompt configs / supplier prompt config logic unchanged.
- Legacy table not dropped; legacy API not disabled.
- No migration-driven file copy/delete; no legacy row deletes for migration.

---

## 13. Observations / blockers

- Production operators should ensure **`aisles.client_supplier_id`** is populated where supplier reference context is expected; otherwise jobs run with **zero** visual references by design.

---

## 14. Recommended next phase

**C8 — Disable legacy writes and hide old inventory reference UI**
