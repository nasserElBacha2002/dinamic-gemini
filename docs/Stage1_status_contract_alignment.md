# Stage 1 — Status and contract alignment (product plan vs API)

Source docs: `Plan implementacion 3.3.md`, `Re diseño 3.3.md`.  
Implementation: `frontend/src/types/statusAlignment.ts`, `frontend/src/types/screenTargets.ts`.

## Current vs target taxonomies (summary)

| Axis | Current source (backend / API) | Current values | Target (doc) | Gap / note |
|------|-------------------------------|----------------|--------------|------------|
| Inventory | `InventoryStatus` | draft, processing, in_review, completed, failed | draft, in_progress, completed, archived | No `archived` in API; `failed` has no doc bucket; processing/in_review → `in_progress` via mapper (approximate). |
| Aisle | `AisleStatus` | created, assets_uploaded, queued, processing, processed, in_review, completed, failed | empty, assets_uploaded, processing, processed, error | Richer API state machine; `created`≈`empty`; post-CV states map to `processed` or `error`. |
| Job | `JobStatus` | queued, running, cancel_*, timed_out, succeeded, failed | *(not in §11)* | Technical lifecycle; not the product aisle taxonomy. |
| Position | `PositionStatus` + `needs_review` | detected, reviewed, corrected, deleted | pending_review, confirmed, corrected, deleted | Derived mapping in `statusAlignment.ts`. |
| Visible review (UI) | Epic `ReviewStatus` | DETECTED, CONFIRMED, … | Doc snake-case result labels | Plan helpers use the doc target strings; Epic model stays for existing UI. |
| Traceability | API | valid, missing, invalid, unvalidated | Quality buckets + low_confidence | `unvalidated` → null traceability bucket in alignment helper. |

## Screen-readiness (contracts)

| Screen | Supported today | Why |
|--------|-----------------|-----|
| Dashboard | Partially | No global KPI/activity API. |
| Inventories list | Partially | Thin `InventoryResponse`. |
| Inventory detail | Partially | Aisles + jobs exist; richer row DTOs TBD. |
| Aisle results | Largely | Positions list + filters. |
| Review queue | Not | No cross-inventory positions endpoint. |
| Result detail | Largely | Detail + review_actions. |
| Metrics / analytics | Partially | Per-inventory metrics; no global trends. |

## Next steps (Stage 2+)

- Backend enum convergence or `display_status`; list/dashboard aggregates; review-queue API.
