# Phase 4.8 — API and Frontend Evidence Contract

## 1. Executive summary

| Item | Status |
|------|--------|
| **Implementation verdict** | **COMPLETE** |
| Code-review corrections | **Closed** — all P1/P2 findings addressed and tested |
| Backend API contract | Implemented — structural `result_evidence` read model + job traceability endpoint |
| Frontend contract | Implemented — `evidence.displayable` is primary gate; details panel added |
| Structural `result_evidence` usage | Authoritative for V3 photo jobs with persisted rows |
| Artifact metadata exposure | Position detail `traceability_artifact` + job traceability endpoint |
| Legacy fallback behavior | Strict fail-closed by default; explicit `allowLegacyEvidenceFallback` for pre-4.8 screens |
| Regression results | Phase 4.8 (24), 4.7 (50), 4.6 (28), 4.5 (79), Artifact/Gemini (66 passed, 1 skipped) — all pass |
| Video traceability | **Out of scope — not implemented** |
| Phase 4.9 status | **Not started** |

## 2. Backend API contract

### Endpoints

1. **Position detail (extended)**  
   `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`  
   Adds optional `evidence` and `traceability_artifact` alongside legacy `evidences[]`.

2. **Job traceability (new)**  
   `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability`  
   Returns `JobTraceabilityResponse` with `traceability.status`, `artifact`, `summary`, and `entities[]`.

### DTO / schema

- `ResultEvidenceViewResponse` — per-entity evidence contract (`displayable`, `traceability_status`, URLs, manifest ids, `source_kind`, provider/model).
- `TraceabilityArtifactMetadataResponse` — `kind`, `published`, `storage_key`, `content_hash`, `size_bytes`, `published_at`, `required`, `status`.
- `TraceabilitySummaryResponse` — row counts aligned with Phase 4.7 (`malformed_identifier`, `unvalidated_unknown`, `artifact_required`, `artifact_published`, …).
- `JobTraceabilityEnvelopeResponse` — typed traceability envelope (`status`, `artifact`, `summary`).
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
- Required `traceability_manifest` is published when manifest store marks it required
- `source_image_id` and resolved `source_asset_id` must match (fail-closed on mismatch)

Structural evidence lookup uses **resolved run context job ID**:

```text
resolved_job_id = run_context.resolved_job_id or run_context.job_id or position.job_id
```

When required artifact is unpublished:

```text
displayable=false
traceability_status=artifact_unavailable
image_access_status=not_allowed
image_url=null
```

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
| Phase 4.8 backend (4 modules) | **24 passed**, 0 failed, 0 skipped |
| Phase 4.7 regression | **43 passed** |
| Phase 4.6 regression | **28 passed** |
| Phase 4.5 regression | **79 passed** |
| Artifact/Gemini regression | **66 passed**, **1 skipped** |
| Phase 4.8 frontend (6 files) | **81 passed** |
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

## 9. Phase 4.8 code-review corrections

| Finding | Resolution |
|---------|------------|
| P1: artifact unavailable must block position detail | `build_evidence_view(job_id=…)` checks required unpublished manifest → `artifact_unavailable`, `displayable=false`, no URLs |
| P1: resolved run context job ID | Position detail uses `resolved_job_id or job_id or position.job_id` for evidence lookup |
| P1: frontend must use `imageUrl` | Panel/viewer render backend `evidenceView.imageUrl`; legacy loader only when `evidenceView` absent |
| P2: artifact metadata in details | Option A: `traceability_artifact` on position detail → `ResultEvidenceDetails` shows status + hash |
| P2: typed traceability envelope | `JobTraceabilityEnvelopeResponse` replaces `dict[str, object]` |
| P2: summary buckets aligned with 4.7 | Added `malformed_identifier`, `unvalidated_unknown`, `artifact_required`, `artifact_published` |
| P2: source_asset vs source_image | Fail-closed mismatch policy in `detect_source_asset_mismatch()` |
| P2: legacy fallback explicit | `allowLegacyEvidenceFallback` option (default false); Phase 4.8 screens fail-closed without `evidenceView` |

### Correction test results

| Suite | Result |
|-------|--------|
| Phase 4.8 backend | 24 passed |
| Phase 4.7 regression | 50 passed |
| Phase 4.6 regression | 28 passed |
| Phase 4.5 regression | 79 passed |
| Artifact/Gemini | 66 passed, 1 skipped |
| Phase 4.8 frontend | 81 passed |
| Backend compileall | pass |
| Frontend build/typecheck/lint | pass (0 lint errors, 10 pre-existing warnings) |

## 10. Remaining risks

- E2E hardening pending (Phase 4.9)
- Historical backfill of structural rows for legacy jobs not in scope
- Crop-level evidence model evolution out of scope
- Large-scale performance audit of traceability endpoint not run

No unresolved Phase 4.8 API/frontend contract issues deferred to 4.9.

## 11. Phase 4.9 readiness

**Ready to begin Phase 4.9 — End-to-End Hardening and Regression Tests.**

Prerequisites met:

- Backend exposes structural evidence read model with fail-closed displayability
- Frontend consumes `displayable` as primary gate
- Artifact metadata safely exposed
- Phase 4.5–4.7 and Artifact/Gemini regressions pass
- Video traceability not started
