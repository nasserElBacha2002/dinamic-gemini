# v3 Contract Alignment (Release 3.2.5 Phase 2)

This document records contract inconsistencies identified in Phase 2 and the implementation notes for their resolution.

---

## Phase 2 closure summary

Phase 2 (active contract hardening) is **closed**. Four narrow blocks were implemented: list/detail `corrected_quantity` alignment, `latest_job` shape alignment (aisle list vs status), canonical typed source-image fields, and `has_evidence` as a guaranteed boolean. Backend and frontend types/mappers were updated; remaining fallbacks are documented and classified below. The repository is ready to proceed to **Phase 3 — Job lifecycle hardening** with the cautions noted.

---

## Implemented contract decisions

| Decision | Backend | Frontend | Verified in repo |
|----------|---------|----------|------------------|
| **corrected_quantity** list/detail coherent | List endpoint computes from display primary product and passes into `position_to_summary`; detail already did. | Uses `corrected_quantity ?? qty`; both list and detail now receive same `corrected_quantity` from API. | `positions.py` list loop passes `corrected_quantity`; `shared.position_to_summary` accepts it. |
| **latest_job** shape aligned | `AisleJobSummary` includes `created_at`; `aisle_to_response` sets it from `Job.created_at`. | Types already had `created_at` on job summary; no mapper change. | `aisle_schemas.AisleJobSummary.created_at`; `shared.aisle_to_response` sets `created_at=latest_job.created_at`. |
| **Source-image typed canonical** | Typed `source_image_id` / `source_image_original_filename` already populated in `position_to_summary` (from summary + enrichment). | `mapPositionDetailToResultDetail` uses typed fields first; falls back to `detected_summary_json` only when typed absent. | `positionToResult.ts`: `typedSourceImageId ?? getSummaryString(...)`. |
| **has_evidence guaranteed** | `has_evidence` always set in `position_to_summary` (both branches) from `primary_evidence_id`. | `PositionSummary.has_evidence` is required (`boolean`); mapper uses it when `typeof === 'boolean'`, else narrow fallback. | `position_schemas.PositionSummaryResponse.has_evidence`; `positionToResult` uses `p.has_evidence` with documented fallback. |

---

## Remaining compatibility fallbacks

These remain in the frontend by design; they are either defensive or for transitional/historical payloads.

| Location | Field / behavior | Why it remains | Classification |
|----------|------------------|----------------|-----------------|
| `positionToResult.ts` | `has_evidence`: `typeof p.has_evidence === 'boolean' ? p.has_evidence : Boolean(primary_evidence_id...)` | Transitional payloads that omit `has_evidence` (e.g. cached or older API). | **Keep** — documented and tested (Case 4). |
| `positionToResult.ts` | `qtySource: p.qtySource ?? 'detected'` | Backend sends it; defensive default if ever missing. | **Keep** — low cost, avoids undefined display. |
| `positionToResult.ts` | Source image: `typedSourceImageId ?? getSummaryString(summaryJson, 'source_image_id')` (same for filename) | Historical or enriched payloads that do not yet populate typed fields. | **Keep** — documented compatibility fallback. |
| `positionToResult.ts` | `entityId = getSummaryString(summaryJson, 'entity_uid')` | Backend has no top-level `entity_uid` on position DTO; only in `detected_summary_json`. | **Defer** — could be typed in a later phase. |
| `positionToResult.ts` | `mapTraceabilityToVisible`: unknown status → `UNVALIDATED` | Backend sends optional `traceability_status`; defensive normalization for unknown values. | **Keep** — avoids broken UI for new backend values. |
| `positionToResult.ts` | `evidences ?? []`, `review_actions ?? []` | Safe default if API omits arrays. | **Keep** — defensive. |
| `jobStatus.ts` | `getJobStatusLabel`: unknown status → capitalized string | Display resilience for job status strings. | **Keep** — display-only, not contract. |

None of these override valid explicit backend values; they only apply when the canonical value is missing or invalid.

---

## Deferred contract issues for later phases

Not fixed in Phase 2; left for Phase 4+ or later consolidation.

| Issue | Files / area | Notes |
|-------|--------------|--------|
| **entity_uid not a typed position field** | Backend: position schema, enrichment. Frontend: `technicalMetadata.entityId` from `detected_summary_json`. | Could add `entity_uid` to `PositionSummaryResponse` and mapper in a later phase. |
| **Evidence/asset storage_path in DTOs** | `EvidenceResponse.storage_path`, `SourceAssetResponse.storage_path` (IMPLEMENTATION_AUDIT §4.3). | Frontend uses file-serving routes, not storage_path; exposure is metadata/infra leak. Phase 4 artifacts alignment. |
| **detected_summary_json still used for enrichment** | Backend: `shared._enrich_position_traceability_from_report` uses `entity_uid` from summary. | Backend enrichment fills typed fields when missing; blob remains for legacy and enrichment. No removal in Phase 2. |
| **Upload adaptation inconsistency** | Inventory upload: fail-fast 422. Aisle assets: skip malformed parts (IMPLEMENTATION_AUDIT §4.2). | Unify in a later 3.2.5 or post-3.2.5 cleanup. |
| **API version string** | `backend/src/api/server.py`: `version="2.0.0"`. | Hygiene; can be updated when releasing v3-only. |
| **Job status enum divergence** | v3 domain `JobStatus` vs legacy `jobs.models.JobStatus` (no cancel states). | Phase 3 job lifecycle hardening scope. |

---

## corrected_quantity missing in list vs present in detail

**Issue**: `GET .../positions` did not populate `corrected_quantity` on each position summary, while `GET .../positions/{position_id}` did populate it from the display primary product. The frontend uses `resolvedQty = corrected_quantity ?? qty`, so the list view could show the uncorrected pipeline quantity while the detail view showed the manually corrected quantity.

**Implementation note (Phase 2 Block 1)**:
- The list contract was aligned with detail. In `backend/src/api/routes/v3/positions.py`, the list endpoint now computes `corrected_quantity` from the same display primary product (first by `created_at`, `id`) and passes it into `position_to_summary(...)`.
- Both list and detail now expose the display primary product's manual override consistently; no schema or response shape change was required.

---

## latest_job shape inconsistency (aisle list vs aisle status)

**Issue**: `GET .../aisles` exposed `latest_job` via `AisleJobSummary` (no `created_at`), while `GET .../aisles/{aisle_id}/status` exposed `latest_job` via `JobSummary` (with `created_at`). The same conceptual object had different shapes and forced consumers to special-case list vs status.

**Implementation note (Phase 2 Block 2)**:
- Aisle list and aisle status now expose aligned `latest_job` timeline fields. `AisleJobSummary` was extended with `created_at`; `aisle_to_response(...)` in `backend/src/api/routes/v3/shared.py` now populates it from the domain `Job`.
- `created_at` is now available in both contracts (`AisleResponse.latest_job` and `AisleStatusResponse.latest_job`). Field set is aligned: `id`, `status`, `created_at`, `updated_at`, `error_message`. No lifecycle or cancellation behavior was changed.

---

## source-image fields: typed vs detected_summary_json

**Issue**: The backend already exposed typed `source_image_id` and `source_image_original_filename` on position/result DTOs, but the frontend still preferred `detected_summary_json` for those values, so the compatibility blob was effectively the source of truth for preview UI.

**Implementation note (Phase 2 Block 3)**:
- Typed source-image fields are now treated as canonical in v3 consumers. In `frontend/src/features/results/mappers/positionToResult.ts`, `mapPositionDetailToResultDetail` prefers `position.source_image_id` and `position.source_image_original_filename`; it falls back to `detected_summary_json` only when typed values are absent (historical compatibility).
- `detected_summary_json` remains in the API and is used only as a compatibility fallback for older or enriched payloads that may not yet populate the typed fields.

---

## has_evidence as guaranteed boolean (list/detail)

**Issue**: The backend declared `has_evidence` as a boolean on the position/result DTO, but the frontend treated it as optional and fell back to `Boolean(primary_evidence_id)`, so the field was not fully trusted as part of the v3 contract.

**Implementation note (Phase 2 Block 4)**:
- `has_evidence` is now treated as a guaranteed boolean field in active v3 consumers. The backend already populates it in both list and detail paths via `position_to_summary(...)` in `backend/src/api/routes/v3/shared.py`.
- Frontend type `PositionSummary` now declares `has_evidence: boolean` (required). The mapper in `frontend/src/features/results/mappers/positionToResult.ts` uses `position.has_evidence` directly when it is a boolean; only transitional payloads that omit the field use the `primary_evidence_id` fallback, which is documented and tested.
