# Frontend Phase 2 — Query Key Stability and Canonicalization

## Scope implemented

- Implemented only Phase 2:
  - query key consistency
  - lightweight canonicalization
  - targeted key factory consolidation
- Not implemented:
  - mutation invalidation strategy redesign (Phase 3)
  - `setQueryData` patching (Phase 5)
  - broad cache policy tuning

## High-priority areas covered

1. `useReviewQueue`
2. `useInventoriesList`
3. queries used by `AislePositionsPage` through `usePositions` / `useResultSummaries`

## Inconsistencies found (before changes)

- `useReviewQueue` used inline key `['reviewQueue', listQuery]` with raw object filters.
- `useInventoriesList` keyed on raw object with defaults merged inline; semantic equivalents (e.g. whitespace-only fields) could fragment cache identity.
- positions/detail/merge-results keys mixed object fragments and direct tuple values; `jobId` whitespace/null equivalents were not consistently collapsed in key identity.

## Changes implemented

### 1) Shared canonicalization utility

- File: `frontend/src/api/queryParamCanonicalization.ts`
- Added:
  - `canonicalizeInventoriesListQuery(...)`
  - `inventoriesListKeyPart(...)`
  - `reviewQueueListKeyPart(...)`
  - `positionsListKeyPart(...)`
  - `canonicalizeOptionalId(...)`

### 2) Key factory consolidation

- File: `frontend/src/api/queryKeys.ts`
- Added targeted key helpers:
  - `inventories.listWithParams(...)`
  - `inventories.positionsList(...)`
  - `inventories.positionDetailScoped(...)`
  - `inventories.mergeResultsForJob(...)`
  - `reviewQueue.all/list(...)`
- Kept compatibility with existing invalidation prefix for review queue by using `['reviewQueue']` as root.

### 3) Hook updates

- `frontend/src/hooks/useInventories.ts`
  - list query now uses canonicalized params for both key and request payload.
- `frontend/src/hooks/useReviewQueue.ts`
  - switched to `queryKeys.reviewQueue.list(reviewQueueListKeyPart(...))`.
- `frontend/src/hooks/usePositions.ts`
  - list key part now comes from shared canonicalizer.
  - detail and merge-results job scope now use canonical `jobId` (`trim` + empty-to-null).

## Test coverage added

- File: `frontend/tests/queryParamCanonicalization.test.ts`
- Covers:
  - inventories canonical defaults + trim equivalence
  - review queue null/empty/value equivalence
  - positions resolver-default vs explicit job scope separation
  - optional id canonicalization (`trim` / null-collapse)

## Deferred for later phases

- Review mutation invalidation fan-out (`useSubmitReviewAction`) remains unchanged (Phase 3 target).
- Analytics params key canonicalization remains partially object-based in `queryKeys.analytics.*` (defer to next pass to keep this phase narrow).
- No mutation strategy layer introduced.

## Safety notes

- Endpoint contracts and request semantics were preserved.
- Canonicalization intentionally mirrors existing query-string builders:
  - trims text where API already trims
  - lowercases fields that API already lowercases (`traceability`, `position_status`)
  - preserves meaningful booleans and numeric filters
  - keeps run-scope identity explicit via `job_id` vs `job_slice=resolver_default`
