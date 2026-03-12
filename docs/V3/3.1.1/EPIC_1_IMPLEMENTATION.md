# Epic 1 — Consolidation of the visible review model (implementation summary)

## Scope implemented

- **Frontend-first:** Result-centric visible types, mappers, and hooks. No backend changes.
- **In scope:** New Result types, position/evidence/detail → Result mappers, hooks exposing Result list/detail, deprecation notes on entity-facing API types.
- **Out of scope:** Full UI redesign, removal of routes, domain merge (unchanged).

---

## Files created

| Path | Purpose |
|------|--------|
| `frontend/src/features/results/types.ts` | ResultSummary, ResultDetail, ResultEvidence, ResultProductInfo, ReviewHistoryItem, ReviewStatus, TraceabilityStatus |
| `frontend/src/features/results/mappers/positionToResult.ts` | mapPositionSummaryToResultSummary, mapPositionDetailToResultDetail, mapEvidenceToResultEvidence, mapProductToResultProductInfo, mapReviewActionToHistoryItem, mapTraceabilityToVisible, mapPositionStatusToReviewStatus |
| `frontend/src/features/results/mappers/index.ts` | Barrel export for mappers |
| `frontend/src/features/results/hooks/useResultSummaries.ts` | useResultSummaries, useResultDetail (wrap position API, return Result model) |
| `frontend/src/features/results/index.ts` | Barrel export for types, mappers, hooks |
| `frontend/tests/resultMappers.test.ts` | 17 tests for mappers and status mapping |
| `docs/V3/3.1.1/EPIC_1_IMPLEMENTATION.md` | This file |

---

## Files modified

| Path | Change |
|------|--------|
| `frontend/src/api/types/responses.ts` | Note that visible model lives in features/results; `@deprecated` on JobEntityListItem and JobEntitiesListResponse for main review flow |
| `frontend/src/pages/JobEntitiesPage.tsx` | Type fix: traceabilityStatusParam narrowed to TraceabilityStatus \| undefined so useJobEntities options type-check |

---

## Visible model (summary)

- **ResultSummary:** id, sku, detectedQty, confidence, reviewStatus, traceabilityStatus, needsReview, updatedAt, hasEvidence (for list table).
- **ResultDetail:** full detail with evidence[], product, reviewHistory[], technicalMetadata (for detail screen).
- **ReviewStatus:** DETECTED | CONFIRMED | NEEDS_REVIEW | MISSING | INVALID | NOT_COUNTABLE (derived from position status + needs_review).
- **TraceabilityStatus:** VALID | MISSING | INVALID | UNVALIDATED (uppercase; mapped from backend lowercase).

---

## Usage for later epics

- **Results list:** Use `useResultSummaries(inventoryId, aisleId)` and render `results` (ResultSummary[]). No need to use raw PositionSummary in new code.
- **Result detail:** Use `useResultDetail(inventoryId, aisleId, positionId)` and render `result` (ResultDetail). Evidence, product, reviewHistory are already shaped.
- **Mapping from API:** Use `mapPositionSummaryToResultSummary`, `mapPositionDetailToResultDetail` from `features/results` if building custom flows.

---

## Verification

- [x] `npm run typecheck` (frontend) passes
- [x] `npm run test` (frontend) passes (64 tests, including 17 resultMappers)
- [x] No backend changes; existing AislePositionsPage and PositionDetailPage unchanged (still use raw API types; can migrate to Result model in Epic 3/4)
- [x] Entity-facing types deprecated in JSDoc only; JobEntitiesPage and v1 entities API still work

---

## Optional next steps (later epics)

- Migrate AislePositionsPage to use `useResultSummaries` and ResultSummary for table rows.
- Migrate PositionDetailPage to use `useResultDetail` and ResultDetail for layout.
- Add KPI helpers that consume ResultSummary[] (Epic 3).
- Add previous/next navigation using results array (Epic 5).
