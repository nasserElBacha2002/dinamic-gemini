# Final architecture review

## Boundary fixes (this phase)

| Rule | Before | After |
|------|--------|-------|
| Domain ↛ pipeline | `traceability_artifact/builder.py` imported `PROVIDER_IMAGE_MANIFEST_ORDER_KEY` from pipeline | Constant owned by `domain/execution_image_manifest.py`; pipeline re-exports |
| Application ↛ API | `llm_cost_snapshot_public.py` imported `LlmCostSnapshotResponse` from API schemas | Model in `application/schemas/llm_cost_snapshot.py`; API re-exports for wire compatibility |

## Guardrails

`backend/tests/architecture/test_layer_import_boundaries.py` AST-scans:

- `src/domain/**` must not import `src.pipeline`, `src.api`, `src.infrastructure`
- `src/application/**` must not import `src.api`
- Spot-checks for the two fixed edges

## Deferred architecture debt

- Split oversized `aisles.py` router (ARCH-003)
- Frontend mega-files (ARCH-004)
- Extreme use-case/pipeline orchestrators (complexity) — extract only with golden tests

## Compatibility

Public API response shapes for LLM cost snapshots and run metadata key `provider_image_manifest_order` unchanged.
