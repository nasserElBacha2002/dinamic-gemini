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

## C7.1 Validation hardening

### Anti-regression tests

Added to **`backend/tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py`**:

- **`test_c71_supplier_pipeline_never_calls_inventory_visual_reference_list_by_inventory`** — `aisle.client_supplier_id` set, in-memory **`supplier_reference_images`** has one row; **`InventoryVisualReferenceRepository`** strict mock raises if **`list_by_inventory`** were invoked via an unwired legacy resolver pair; **`InventoryVisualReferenceResolver.resolve_for_inventory`** and concrete **`MemoryInventoryVisualReferenceRepository` / `SqlInventoryVisualReferenceRepository.list_by_inventory`** are patched to fault during **`build_pipeline_input`**; asserts job metadata resolves the supplier reference and **`strict_inventory_visual_repo.list_by_inventory`** stays unused.
- **`test_c71_supplier_with_no_images_builds_empty_visual_references`** — supplier id set, **`list_by_supplier`** returns **`[]`**; **`resolve_for_inventory`** patch forbids legacy path; asserts empty **`visual_references`** and successful **`JobInput`**.
- **`test_c71_no_supplier_skips_supplier_repo_lookup_and_legacy_fallback`** — **`client_supplier_id`** **`None`**; asserts **`list_by_supplier`** never called and legacy resolver patch unused.

Builder-level coverage remains for supplier-empty (**`test_builder_with_no_visual_references`**) and no-supplier (**`test_builder_with_no_supplier_skips_resolution`**) in **`test_aisle_analysis_context_builder.py`**.

### Grep audit (`rg`, scoped paths)

**`list_by_inventory`** under **`src/infrastructure`**, **`src/application`**, **`src/jobs`:**

| Bucketing | Occurrences |
|-----------|--------------|
| **Aisle / session / analytics `list_by_inventory`** | Normal inventory-scoped listing (**`AisleRepository`**, **`CaptureSessionRepository`**, **`memory_analytics_repository`**, **`inventory_metrics_service`**, related use cases). Not **`inventory_visual_references`**. |
| **`inventory_visual_references`** | **`InventoryVisualReferenceRepository.list_by_inventory`** in **`ports/repositories.py`** (contract); implementations **`memory_inventory_visual_reference_repository`**, **`sql_inventory_visual_reference_repository`**; **`upload_inventory_visual_references`** use case; **`inventory_visual_reference_resolver`** (**legacy service**, not imported by **`src/infrastructure/pipeline`** or **`src/jobs`** active aisle executor after C7). |
| **`src/jobs`** | No **`list_by_inventory`** hits — worker pipeline path does not list legacy inventory refs. |

**`InventoryVisualReferenceResolver`** under **`src/infrastructure`**, **`src/jobs`**, **`src/application`:**

| Bucket | Finding |
|--------|---------|
| **Definition only** | **`src/application/services/inventory_visual_reference_resolver.py`** — not referenced by **`v3_job_executor`**, **`v3_process_aisle_pipeline_runner`**, or **`jobs/`**. |

**`inventory_visual_reference_repo`** under **`src/infrastructure`**, **`src/jobs`**, **`src/runtime`:**

| Bucket | Finding |
|--------|---------|
| **Legacy API / DI** | **`runtime/app_container.py`**, **`runtime/v3_deps.py`**, **`runtime/__init__.py`** expose **`get_inventory_visual_reference_repo()`** for inventory visual reference routes and legacy uploads (**expected until C8**). |
| **Jobs / pipeline** | **`worker.py`** does **not** pass **`inventory_visual_reference_repo`** into **`V3JobExecutor`** after C7 (`grep` confirms none under **`src/jobs`** besides unrelated hits — none). |

**Active pipeline risk:** **None identified** — **`inventory_visual_reference_repo.list_by_inventory`** is not part of the v3 **`process_aisle`** executor/runner stack.

### Validation commands / results (recorded pass unless noted)

From **`backend/`** (environment: sandbox **`Python 3.9.6`**):

| Command | Result |
|---------|--------|
| **`pytest`** targeted modules: resolver, aisle builder, **`test_v3_job_executor_input_resolution`**, **`test_v3_process_aisle_pipeline_runner`** (**7** tests incl. C7.1), **`test_run_metadata`** | **Pass** — **35** tests |
| **`pytest`** **`test_upload_inventory_visual_references`**, **`test_manage_inventory_visual_references`** | **Pass** — **15** tests |
| **`pytest`** **`test_upload_supplier_reference_images`**, **`test_manage_supplier_reference_images`** | **Pass** — **20** tests |
| **`pytest tests/api/test_inventory_visual_references_api.py`**, **`tests/api/test_supplier_reference_images_api.py`** | **Not run in this environment** — API **`conftest`** import fails on Python **3.9** (`Settings | None` typing). Run under **Python 3.10+** / CI. |
| **`pytest --collect-only`** | **Interrupted**: **24** collection errors on this interpreter (same **`\|` union** / dataclass issues); **1502** tests collected before failures — CI matrix expected green on supported Python. |
| **`ruff check src tests scripts`** | **Pass** (after import sort on touched test file). |

### Confirmation

- **`inventory_visual_reference_repo.list_by_inventory`** is **not** used by **`V3JobExecutor`** / **`V3ProcessAislePipelineRunner`** / **`worker`** pipeline wiring post-C7; grep + tests corroborate.

---

## 14. Recommended next phase

**C8 — Disable legacy writes and hide old inventory reference UI**
