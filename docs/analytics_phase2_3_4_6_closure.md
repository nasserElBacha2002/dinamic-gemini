# Analytics Phase 2 / 3 / 4 / 6 Closure

## Scope

This note closes the already-advanced analytics phases that are ready for consolidation:

- Phase 2 — backend analytics refactor
- Phase 3 — inventory / aisle scope correctness
- Phase 4 — frontend layout redesign
- Phase 6 — inventory performance redesign

This pass intentionally does **not** expand:

- Phase 5 — operational visual evolution
- Phase 7 — final aisle-table redesign beyond the compact delivered version
- Phase 8 — final quality-pattern redesign beyond the delivered improvement

## What was fixed in this pass

### Phase 2

- confirmed the Phase 4 persistence work is properly versioned with:
  - `backend/src/database/migrations/versions/0008_add_position_review_resolution.sql`
- kept migration readiness aligned with the existing numbered SQL migration workflow
- tightened backend contract/docs wording so `unknown` is documented as:
  - explicit
  - persisted
  - terminal
- kept `invalid` explicitly documented as still blocked from a separate terminal review outcome
- cleaned stale DTO wording that still described pre-unknown reviewed-outcome semantics

### Phase 3

- clarified the inventory filter UX copy:
  - `All inventories` -> `All inventories in scope`
- made the scope summary line more explicit:
  - `Inventory scope: ...`
  - `Aisle scope: ...`
  - `Positions in scope: ...`
- kept the existing coherent behavior:
  - inventory drives page-wide scope
  - aisle options depend on selected inventory
  - invalid aisle selection resets when inventory changes

### Phase 4

- preserved the approved structure:
  1. filters
  2. KPI grid
  3. operational visuals
  4. inventory performance
  5. quality patterns + aisle attention
- no new visual redesign was introduced
- tightened aisle-section subtitle copy to match the current delivered contract

### Phase 6

- kept `Inventory performance` as the primary comparison table
- made `Unknown rate` sortable when present
- kept newer backend fields primary with legacy-safe fallbacks
- aligned the aisle attention table to the already-delivered backend contract by rendering:
  - `unknown_count`
  - `manual_corrections_count`

## Closure status

### Phase 2

Status: `complete`

Why:
- additive contracts are in place
- explicit unknown persistence is now wired through analytics
- migration/versioning is properly closed
- remaining broader formula-centralization work is an optimization/future cleanup, not a closure blocker

### Phase 3

Status: `complete`

Why:
- inventory acts as a real scope driver across the page
- aisle selection depends on inventory
- invalid aisle resets correctly
- scope summary is truthful
- inventory filter copy no longer feels transitional

### Phase 4

Status: `complete`

Why:
- the approved page hierarchy is intact
- old blocks are not part of the delivered main layout
- no stale duplicate sections were introduced in this pass

### Phase 6

Status: `complete`

Why:
- inventory performance remains promoted and paginated
- sorting is coherent
- newer fields are used with safe fallbacks
- truthful `unknown_rate` can now render when backend provides it

## Intentionally deferred

The following remain for the next prompt and were not expanded here:

- Phase 5:
  - operational visual sophistication beyond the current useful version
- Phase 7:
  - final aisle-table redesign beyond the compact/paginated delivered version
- Phase 8:
  - final quality-pattern redesign beyond the current ordering/preparation

## Remaining blocked item

- distinct persisted `invalid` terminal review outcome

Current status:
- `unknown` is now explicit and persisted
- `invalid` is still not modeled separately from `delete_position`
- because of that, invalid remains a documented business-model blocker rather than a closure issue for
  Phases 2 / 3 / 4 / 6
