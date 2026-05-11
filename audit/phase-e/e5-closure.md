# E5 closure — Supplier reference image resolution in v3 pipeline

**Date:** 2026-05-11  
**Status:** `PHASE_E5_CLOSED_READY_FOR_E6`

## 1. Executive summary

Supplier reference images are now a **formal, tested, traceable** path for v3 aisle jobs: resolution uses `aisles.client_supplier_id` against `supplier_reference_images`, attaches rows only as `visual_references` (never primary evidence), skips safely when the inventory has no `client_id`, when the aisle has no supplier, when there are no active rows, or when individual files are unreadable, and records **stable metadata** on `AnalysisContext` for logs and E4 effective-prompt traceability. `V3JobExecutor` loads the inventory and passes `inventory_client_id` into context construction. Read-only findings are in `e5-read-only-audit.md`.

## 2. Files changed

| Area | Path |
|------|------|
| Context + metadata | `backend/src/application/services/aisle_analysis_context_builder.py` |
| v3 runner API | `backend/src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py` |
| v3 executor wiring | `backend/src/infrastructure/pipeline/v3_job_executor.py` |
| Tests | `backend/tests/application/services/test_aisle_analysis_context_builder.py`, `test_v3_process_aisle_pipeline_runner.py`, `test_v3_job_executor_analysis_context.py`, `test_v3_job_executor_phase5.py`, `test_hybrid_global_analysis_strategy_phase4.py`, `test_hybrid_analysis_prompt_e4_integration.py` |
| Audit | `audit/phase-e/e5-read-only-audit.md`, this closure |

## 3. Resolution flow (final)

1. `V3JobExecutor._v3_resolve_pipeline_inputs_or_abort` loads `Inventory` by `aisle.inventory_id` and reads `client_id`.  
2. `V3ProcessAislePipelineRunner.build_analysis_context(aisle, inventory_client_id=…)` delegates to `AisleAnalysisContextBuilder.build(…)`.  
3. If `inventory_client_id` is blank → no repo call for references; empty `visual_references`; status `fallback_inventory_without_client`.  
4. If aisle `client_supplier_id` is blank → same with `fallback_aisle_without_client_supplier`.  
5. Else `SupplierReferenceImageResolver.resolve_for_supplier` reads `supplier_reference_images` via `SupplierReferenceImageRepository.list_by_supplier`.  
6. `build_pipeline_input` resolves blob paths into `resolved_path` (unchanged); hybrid stage uses `prepare_visual_reference_inputs` for LLM attachments (`role: visual_reference`) and execution log counts.

## 4. Fallback / error behavior

| Situation | Behavior |
|-----------|----------|
| Inventory missing or `client_id` empty | No supplier reference attachments; `supplier_reference_resolution_status=fallback_inventory_without_client`; job continues |
| Aisle `client_supplier_id` empty | No references; `fallback_aisle_without_client_supplier` |
| Supplier has zero active images | No references; `fallback_no_active_reference_images` |
| Reference file missing / unreadable | Attachment logged with `resolved: false`; image skipped; job continues if primary evidence exists (existing prep behavior) |
| Supplier / client ownership mismatch for **images** | Not validated here (same as pre-E5); supplier **prompt** ownership remains E4 resolver domain |
| Primary evidence missing | Unchanged pipeline rules |

## 5. Tests added / updated

- **Builder:** inventory-without-client skip, primary vs reference separation, metadata for all fallback paths.  
- **Runner:** `inventory_client_id` on happy-path tests; new `test_e5_inventory_without_client_skips_supplier_reference_images`.  
- **Executor fixtures:** inventories include `client_id` where references are expected.  
- **Hybrid bundle:** two resolved refs + primary attachment role separation; missing file → `resolved: false`.  
- **E4 + E5:** `test_e5_e4_combined_image_ids_supplier_prompt_and_visual_reference_bundle` (manifest image IDs + `supplier_editable_instructions_e4` + visual reference bundle).

## 6. Validation commands and results

Run from `backend/` after checkout:

```bash
python3 -m ruff check src tests
python3 -m pytest tests/application/services/test_supplier_reference_image_resolver.py \
  tests/application/services/test_aisle_analysis_context_builder.py \
  tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py \
  tests/test_hybrid_global_analysis_strategy_phase4.py \
  tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py \
  tests/infrastructure/pipeline/test_v3_e4_supplier_resolution_abort.py \
  tests/infrastructure/pipeline/test_v3_job_executor_analysis_context.py
```

**Recorded run:** `ruff check src tests` — exit 0. Targeted `pytest` slice — **45 passed, 1 skipped** (~5.3s).

## 7. Manual runtime validation

Not executed in this environment. Use the E4-style checklist: new inventory **with** `client_id`, aisle with `client_supplier_id`, active supplier prompt, 1–2 reference images, 3–5 aisle photos, `process_aisle` — expect `attachment_summary` primary + visual counts, `visual_reference_attachments` with `role: visual_reference`, `resolved: true` when blobs exist, and `enrichments_applied` including `supplier_editable_instructions_e4` (and `image_id_traceability_v31` for photos manifests).

## 8. E4 compatibility

Supplier prompt composition is unchanged; combined test asserts image-id enrichment + E4 enrichment + visual reference bundle together.

## 9. Remaining risks / debt

- **Cross-client supplier link** on an aisle is not rejected at reference-image load time (documented).  
- **Double `list_by_supplier`** (builder + pipeline input) remains for path resolution; acceptable for clarity vs micro-optimization.

## 10. Recommendation

```text
PHASE_E5_CLOSED_READY_FOR_E6
```
