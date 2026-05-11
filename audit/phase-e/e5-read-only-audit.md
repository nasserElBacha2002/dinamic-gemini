# E5 — Read-only audit: supplier reference images in v3 pipeline

**Scope:** Supplier-scoped reference images for aisle analysis (Phase C7 baseline + E5 formalization).  
**Date:** 2026-05-11 (pre-implementation snapshot; E5 code changes close gaps noted in §5 and §7.)

## 1. Where is `SupplierReferenceImageResolver` constructed?

- `V3JobExecutor` constructs `SupplierReferenceImageResolver(supplier_reference_image_repo)` and `AisleAnalysisContextBuilder(resolver)`, then passes both into `V3ProcessAislePipelineRunner` (see `v3_job_executor.py`).

## 2. Is it wired into `V3JobExecutor`, `AisleAnalysisContextBuilder`, or another path?

- **AisleAnalysisContextBuilder** calls `resolve_for_supplier(aisle.client_supplier_id)` when building `AnalysisContext`.
- **V3ProcessAislePipelineRunner.build_pipeline_input** calls `supplier_reference_image_repo.list_by_supplier` again to build `references_by_id` for `resolve_visual_reference_paths` (artifact resolution).
- **V3JobExecutor** delegates `build_analysis_context` to the runner (no direct resolver use).

## 3. Which repository / table is the source of reference images?

- Port: `SupplierReferenceImageRepository` → persistence table **`supplier_reference_images`** (see migrations and SQL repository).

## 4. Does it use `aisles.client_supplier_id` as the supplier scope?

- Yes. Resolution keys off `Aisle.client_supplier_id` (trimmed); blank / null skips supplier repo access in the runner’s path.

## 5. Edge cases (pre-E5 behavior where noted)

| Case | Pre-E5 behavior | E5 target |
|------|-----------------|-----------|
| Inventory has no `client_id` | References could still load if aisle had `client_supplier_id` (no inventory gate) | Continue without references; metadata `fallback_inventory_without_client` |
| Aisle has no `client_supplier_id` | Empty `visual_references`; no repo call in runner | Same + explicit status in metadata |
| Supplier has no active rows | Empty list | Same + `fallback_no_active_reference_images` |
| Blob/file missing after DB row | `resolve_visual_reference_paths` may leave unresolved; `prepare_visual_reference_inputs` logs warning, `resolved: false`, skips load | Same; job continues if primary evidence exists |
| Supplier belongs to another client | Not validated at reference-image layer (aisle carries `client_supplier_id`) | Documented risk; E4-style ownership checks apply to **supplier prompt**, not reference list |
| Primary evidence missing | Unchanged pipeline rules (executor may fail for other reasons) | Unchanged |

## 6. Are visual references added to `AnalysisContext.visual_references`?

- Yes, as `VisualReferenceContext` rows with `role="supplier_reference"` (constant `ROLE_SUPPLIER_REFERENCE`).

## 7. Are they excluded from `primary_evidence`?

- Yes. Aisle photos/videos are assembled separately as `AnalysisImage` / frames; supplier images only appear under `visual_references`. LLM attachment logging uses `role: "visual_reference"` for those attachments (see `prepare_visual_reference_inputs`).

## 8. Does “Analysis request prepared” include counts and context?

- **HybridGlobalAnalysisStrategy._analyze_once** logs `attachment_summary` (`primary_evidence_count`, `visual_reference_count`, `total_count`), `visual_reference_attachments`, and `context_instruction` (joined from `analysis_context.instructions`) when `execution_log` is present.

## 9. Persistence / artifacts visibility

- Resolved paths are written into serialized `analysis_context` inside `JobInput.metadata` for the hybrid run. Execution log carries redacted analysis request payload (not full prompt bodies per policy).

## 10. Existing tests (sample)

- `tests/application/services/test_supplier_reference_image_resolver.py`
- `tests/application/services/test_aisle_analysis_context_builder.py`
- `tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py` (C7.1 supplier path)
- `tests/test_hybrid_global_analysis_strategy_phase4.py` (`_prepare_hybrid_llm_visual_bundle`)
- `tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py` (E4 prompt + composition)

## Gaps addressed by E5 implementation (see `e5-closure.md`)

- Thread **`inventory.client_id`** into `build_analysis_context` so inventories without a client do not attach supplier reference images.
- Stable **metadata** keys: `reference_source`, `client_supplier_id`, `supplier_reference_image_count`, `supplier_reference_resolution_status`.
- Expanded **pytest** coverage for fallbacks, unreadable files, primary vs reference roles, and E4+E5 combined trace.

*(Implemented in the same change set as this audit file’s companion closure document.)*
