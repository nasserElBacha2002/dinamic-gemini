# Phase 4.8 — API and Frontend Evidence Contract

## 1. Executive summary

| Item | Status |
|------|--------|
| **Implementation verdict** | **COMPLETE** |
| Backend API contract | Implemented — structural `result_evidence` read model + job traceability endpoint |
| Frontend contract | Implemented — `evidence.displayable` is primary gate; details panel added |
| Structural `result_evidence` usage | Authoritative for V3 photo jobs with persisted rows |
| Legacy fallback behavior | Fail-closed: `legacy_unavailable`, no image without explicit safe legacy path |
| Artifact metadata exposure | Safe metadata on job traceability endpoint (no credentials/raw payloads) |
| Security posture | Fail-closed displayability; no signed URLs for non-displayable evidence |
| Regression results | Phase 4.7 (43), 4.6 (28), 4.5 (79), Artifact/Gemini (66 passed, 1 skipped) — all pass |
| Video traceability | **Out of scope — not implemented** |
| Phase 4.9 status | **Not started** |

## 2. Backend API contract

### Endpoints

1. **Position detail (extended)**  
   `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`  
   Adds optional `evidence: ResultEvidenceViewResponse` alongside legacy `evidences[]`.

2. **Job traceability (new)**  
   `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability`  
   Returns `JobTraceabilityResponse` with `traceability.status`, `artifact`, `summary`, and `entities[]`.

### DTO / schema

- `ResultEvidenceViewResponse` — per-entity evidence contract (`displayable`, `traceability_status`, URLs, manifest ids, `source_kind`, provider/model).
- `TraceabilityArtifactMetadataResponse` — `kind`, `published`, `storage_key`, `content_hash`, `size_bytes`, `published_at`, `required`, `status`.
- `TraceabilitySummaryResponse` — row counts (`valid`, `invalid`, `missing`, `unvalidated`, `displayable`, `not_displayable`, classification buckets).
- `JobTraceabilityResponse` — job-scoped aggregate.

### Source-of-truth rules

1. Structural `result_evidence` rows (authoritative for new V3 photo jobs).
2. Durable `traceability_manifest` artifact metadata.
3. Legacy JSON fields only as backward-compatible fallback (not for displayability).

### Displayability rules

`displayable=true` only when:

- `has_valid_evidence == true`
- `role == primary_evidence`
- `traceability_status == valid`
- `source_image_id` present
- `source_asset_id` present or resolvable
- Image URL resolution succeeds

Reference/invalid/missing/unvalidated → `displayable=false`. No structural row → `legacy_unavailable`. URL failure → `displayable=false`, `image_access_status=url_unavailable` without mutating traceability truth.

### Legacy compatibility

- Existing `evidences[]`, `traceability`, and position JSON fields unchanged.
- New `evidence` field additive on position detail.
- Legacy results without structural rows: `source_kind=unavailable`, `displayable=false`.

### Artifact metadata

Exposed via job traceability when published: kind, published flag, storage key, content hash, size, published_at, required, status. No bucket credentials or raw artifact bytes.

### Security filtering

- No local filesystem paths in responses.
- No provider raw responses or prompt text.
- `image_url` / `thumbnail_url` only when `displayable=true`.
- Security tests assert response JSON excludes sensitive patterns.

## 3. Frontend contract

### Types

- `ResultEvidenceView`, `EvidenceTraceabilityStatus`, `EvidenceSourceKind`, `ImageAccessStatus` in `features/results/types.ts`.
- API mirror types in `api/types/responses.ts`.

### Mapper behavior

- `positionToResult.ts` maps API `evidence` → `evidenceView` on `ResultDetail`.
- Does not infer displayability from `source_image_id`, `image_url`, or legacy crop fields when `evidenceView` is present.

### Eligibility behavior

- `evidenceEligibility.ts`: primary gate is `evidenceView.displayable === true`.
- Legacy path only when `evidenceView` absent (fail-closed).

### UI states

| State | Component behavior |
|-------|-------------------|
| VALID / displayable + URL | Image viewer |
| VALID / displayable + no URL | Non-blocking “Evidence unavailable” |
| INVALID | Warning, no image |
| MISSING | “No evidence returned” |
| UNVALIDATED | Validation warning |
| REFERENCE / invalid role | “Reference image rejected” |
| LEGACY_UNAVAILABLE | Legacy traceability message |
| ARTIFACT_UNAVAILABLE | Artifact status in details panel |

### Details panel

`ResultEvidenceDetails.tsx` shows audit-safe fields: traceability status/warning, manifest ids, source ids, provider/model, artifact hash/status.

### Legacy behavior

Missing structural contract → safe message, no broken image cards.

## 4. Displayability matrix

| Backend status | Role | has_valid_evidence | image_url | Frontend state | Image shown |
|----------------|------|-------------------:|-----------|----------------|-------------|
| valid | primary_evidence | true | present | VALID / displayable | Yes |
| valid | primary_evidence | true | absent | VALID / URL unavailable | No |
| invalid | reference_image | false | absent | Reference rejected | No |
| invalid | unknown | false | absent | INVALID warning | No |
| missing | primary_evidence | false | absent | MISSING empty state | No |
| unvalidated | primary_evidence | false | absent | UNVALIDATED warning | No |
| legacy_unavailable | — | false | absent | LEGACY_UNAVAILABLE | No |
| artifact_unavailable | — | — | absent | TRACEABILITY_ARTIFACT_UNAVAILABLE | No |

## 5. Security and privacy

API and frontend do **not** expose:

- Local absolute paths
- Provider raw responses
- Prompt text
- Credentials
- Image bytes in JSON
- Signed URLs for non-displayable evidence

## 6. Backward compatibility

| Legacy field | Status |
|--------------|--------|
| `evidences[]` | Retained |
| `traceability` on position | Retained |
| `source_image_id` in JSON | Retained (not used for display gate) |
| New `evidence` on position detail | Additive |
| Job `/traceability` endpoint | New read-only |

## 7. Tests

### Added

**Backend**

- `tests/application/test_result_evidence_read_model_phase48.py`
- `tests/api/test_result_evidence_contract_phase48.py`
- `tests/api/test_traceability_summary_phase48.py`
- `tests/api/test_evidence_security_phase48.py`

**Frontend**

- `tests/traceabilityEvidenceContract.test.ts`
- `tests/ResultEvidenceDetails.test.tsx`

### Updated

- `tests/evidenceEligibility.test.ts`, `resultMappers.test.ts`, `ResultEvidencePanel.test.tsx`, `ResultEvidenceViewer.test.tsx`
- Typecheck fixture updates in `ResultsTable.test.tsx`, `ResultSummaryCard.test.tsx`, `AislePositionsPage.test.tsx`, `ResultReviewActions.test.tsx`, `resultPriority.test.ts`, `resultsOverviewSelectors.test.ts`

### Commands and exact results

| Suite | Result |
|-------|--------|
| Phase 4.8 backend (4 modules) | **15 passed**, 0 failed, 0 skipped |
| Phase 4.7 regression | **43 passed** |
| Phase 4.6 regression | **28 passed** |
| Phase 4.5 regression | **79 passed** |
| Artifact/Gemini regression | **66 passed**, **1 skipped** |
| Phase 4.8 frontend (6 files) | **79 passed** |
| Backend `compileall` | **pass** |
| Frontend `npm run build` | **pass** |
| Frontend `npm run lint` | **0 errors**, 10 warnings (pre-existing) |
| Frontend `npm run typecheck` | **pass** |
| Backend `ruff check .` | 100 pre-existing repo issues (not introduced by Phase 4.8) |

## 8. Files changed

### Backend — domain / application

- `backend/src/domain/result_evidence/display.py` — fail-closed displayability rules
- `backend/src/application/services/result_evidence_query_service.py` — read model assembly

### Backend — API

- `backend/src/api/schemas/result_evidence_schemas.py` — DTOs
- `backend/src/api/mappers/result_evidence_mapper.py` — read model → response
- `backend/src/api/schemas/position_schemas.py` — optional `evidence` field
- `backend/src/api/routes/v3/positions.py` — inject evidence on detail
- `backend/src/api/routes/v3/aisles.py` — `/traceability` endpoint
- `backend/src/api/dependencies.py` — query service wiring

### Backend — tests

- Four Phase 4.8 test modules (see §7)

### Frontend

- Types, mappers, eligibility, panel/viewer/details components, i18n, tests

## 9. Remaining risks

- E2E hardening pending (Phase 4.9)
- Historical backfill of structural rows for legacy jobs not in scope
- Crop-level evidence model evolution out of scope
- Large-scale performance audit of traceability endpoint not run

No unresolved Phase 4.8 API/frontend contract issues deferred to 4.9.

## 10. Phase 4.9 readiness

**Ready to begin Phase 4.9 — End-to-End Hardening and Regression Tests.**

Prerequisites met:

- Backend exposes structural evidence read model with fail-closed displayability
- Frontend consumes `displayable` as primary gate
- Artifact metadata safely exposed
- Phase 4.5–4.7 and Artifact/Gemini regressions pass
- Video traceability not started
