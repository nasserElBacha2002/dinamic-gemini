# Stage 1 — Status and contract alignment (product plan vs API)

Source docs: `Plan implementacion 3.3.md`, `Re diseño 3.3.md`.  
Code: `frontend/src/types/statusAlignment.ts`, `frontend/src/types/screenTargets.ts`, `frontend/src/constants/reviewThresholds.ts`.

## What this layer is

Target taxonomies in `screenTargets.ts` are **product/UI alignment labels** from the implementation plan. They are **not** a verbatim copy of backend lifecycle enums (`api/types/shared.ts`). Mappers translate wire values into the smallest set of plan labels for future Dashboard / Review Queue / Metrics — often **approximate**.

## Mapping hazards (read before aggregating KPIs)

### Result review: `target === 'confirmed'` is overloaded

The plan uses a single label `confirmed` for “settled without pending review.” In the API that corresponds to two different situations:

| API | Meaning |
|-----|--------|
| `reviewed` | Human explicitly confirmed (or equivalent terminal review). |
| `detected` + `needs_review === false` | No human review required (auto path / policy). |

The alignment result includes **`resolutionKind`**: `human_confirmed` vs `auto_accepted`. **Do not** merge those in metrics or badges without an explicit product decision — `isApproximate` alone does not capture this.

### Aisle: richer states collapse to fewer plan buckets

Examples: `in_review` and `completed` both map to plan `processed` with `isApproximate: true`. **Operational truth** remains in the raw API status — use `raw` (and backend fields) for drill-down, not only `target`.

### Inventory: `failed` has no plan bucket

`target` is `null`; show wire status or a dedicated “failed” treatment — do not invent a plan enum value.

### Quality: two dimensions, not one enum

Traceability (`valid_traceability` / `invalid_traceability` from API valid/missing/invalid) and **low confidence** (confidence vs shared threshold) are **orthogonal**. `deriveQualityAlignmentSignals` returns both; a row can be low-confidence and valid-traceability. The old flat `TARGET_QUALITY_STATUSES` list was misleading — replaced by `TRACEABILITY_PLAN_LABELS` + `lowConfidence` flag pattern.

### Threshold drift

`LOW_CONFIDENCE_THRESHOLD` lives only in `frontend/src/constants/reviewThresholds.ts` (re-used by Results filters/KPIs and alignment).

## Current vs target taxonomies (summary)

| Axis | Current source (backend / API) | Target (doc) | Notes |
|------|-------------------------------|--------------|--------|
| Inventory | draft, processing, in_review, completed, failed | draft, in_progress, completed, archived | See mapper + `isApproximate`. |
| Aisle | created … failed | empty, assets_uploaded, processing, processed, error | Collapses; see above. |
| Job | queued … failed | *(not §11 product taxonomy)* | Job chips ≠ aisle product status. |
| Position + needs_review | detected, reviewed, corrected, deleted | pending_review, confirmed, corrected, deleted | Use `resolutionKind` for `confirmed`. |
| Traceability + confidence | API + numeric | traceability labels + low-confidence signal | Two dimensions. |

## Screen-readiness (contracts)

| Screen | Supported today | Why |
|--------|-----------------|-----|
| Dashboard | Partially | No global KPI/activity API. |
| Inventories list | Partially | Thin `InventoryResponse`. |
| Inventory detail | Partially | Aisles + jobs; richer row DTOs TBD. |
| Aisle results | Largely | Positions list + filters. |
| Review queue | Not | No cross-inventory positions endpoint. |
| Result detail | Largely | Detail + review_actions. |
| Metrics / analytics | Partially | Per-inventory metrics; no global trends. |

## Next steps (Stage 2+)

- Backend `display_status` or enum convergence where product requires it.
- List/dashboard aggregates; review-queue query API.
