# Release 3.2.5 — Phase 8: Final Frontend Alignment

**Purpose**: Document the frontend contract inventory, type alignment to the consolidated backend model, fallback classification, and interpretation rules so the UI represents backend semantics accurately and remains stable for historical reads.

**Related**: `POSITION_RESULT_CONTRACT.md`, `REVIEW_OPERATIONAL_CONSISTENCY.md`, `JOB_LIFECYCLE_3_2_5.md`, `DEBUGGING_AND_OBSERVABILITY.md`.

---

## 1. Frontend contract inventory

### 1.1 API types (raw v3 contracts)

| Layer | File | Main types | Notes |
|-------|------|------------|--------|
| Responses | `frontend/src/api/types/responses.ts` | `Inventory`, `Aisle`, `AisleJobSummary`, `JobSummary`, `PositionSummary`, `PositionDetailResponse`, `EvidenceSummary`, `ReviewActionSummary`, `ExecutionLogEvent`, `ExecutionLogResponse` | Raw response shapes; PositionSummary has `qty` (required), `qtySource`, `corrected_quantity`, `has_evidence`, traceability fields. |
| Requests | `frontend/src/api/types/requests.ts` | `CreateInventoryRequest`, `CreateAisleRequest`, `ReviewActionRequest` | Minimal; review action uses `action_type`, optional `corrected_quantity`, `sku`, etc. |
| Shared | `frontend/src/api/types/shared.ts` | `JobStatus`, `PositionStatus`, `AisleStatus`, `InventoryStatus`, `ApiTraceabilityStatus`, `ReviewActionType`, `EvidenceType` | Backend-aligned enums; `JOB_STATUSES` includes `cancel_requested`, `canceled`, `timed_out`. |

### 1.2 Visible (domain) model and mappers

| Layer | File | Types / functions | Notes |
|-------|------|-------------------|--------|
| Result types | `frontend/src/features/results/types.ts` | `ResultSummary`, `ResultDetail`, `ResultEvidence`, `ReviewHistoryItem`, `ReviewStatus`, `TraceabilityStatus` | Visible model: camelCase, uppercase traceability/review status; `resolvedQty` = corrected_quantity ?? qty; `systemQty` required (number \| null). |
| Position → Result | `frontend/src/features/results/mappers/positionToResult.ts` | `mapPositionSummaryToResultSummary`, `mapPositionDetailToResultDetail`, `mapEvidenceToResultEvidence`, `mapReviewActionToHistoryItem`, `mapTraceabilityToVisible`, `mapPositionStatusToReviewStatus` | Single place API → visible; uses `getSummaryString` for compatibility fallbacks from detected_summary_json. |
| detected_summary | `frontend/src/features/results/mappers/detectedSummary.ts` | `getSummaryString`, `getSummaryNumber` | Safe accessors for optional blob; used only when typed fields are missing. |

### 1.3 Job and status helpers

| Layer | File | Exports | Notes |
|-------|------|--------|--------|
| Job status | `frontend/src/utils/jobStatus.ts` | `getJobStatusLabel`, `getJobStatusColor` | All v3 job statuses covered (queued, running, cancel_requested, canceled, timed_out, succeeded, failed); no flattening of cancel states. |
| Aisle status | `frontend/src/utils/aisleStatus.ts` | (used in InventoryDetail) | Aisle lifecycle labels/colors. |
| Review status | `frontend/src/features/results/utils/reviewStatusDisplay.ts` | `getReviewStatusLabel`, `getReviewStatusColor` | Maps visible ReviewStatus to label/color; NEEDS_REVIEW, CONFIRMED, INVALID, etc. |
| Traceability | `frontend/src/features/results/utils/traceabilityDisplay.ts` | `visibleTraceabilityToApiStatus` | Maps visible uppercase → API lowercase for chip. |

### 1.4 Selectors and filters

| Layer | File | Exports | Notes |
|-------|------|--------|--------|
| KPI | `frontend/src/features/results/selectors/resultsKpi.ts` | `computeResultsKpi`, `ResultsKpi` | Aggregates needsReview, traceability, qtyZero (detectedQty === 0), withEvidence, lowConfidence. |
| Filters | `frontend/src/features/results/selectors/resultsFilters.ts` | `filterResults`, `ResultsFilterKind` | Filter by needs_review, valid_traceability, non_valid_traceability, qty_zero, low_confidence. |

### 1.5 Pages and views

| Page | File | Consumes | Notes |
|------|------|----------|--------|
| Inventories list | `pages/InventoriesList.tsx` | Inventory[] | No job/position types. |
| Inventory detail | `pages/InventoryDetail.tsx` | Aisle[], JobSummary (latest_job), execution log | Job chip uses getJobStatusLabel/Color; Process disabled by aisle status (queued/processing); no Cancel job button. Execution log empty message: "No log entries yet. The job may not have started or the log file is not available." |
| Results list | `pages/AislePositionsPage.tsx` | ResultSummary[] via useResultSummaries, KPI, filters | List uses same visible model as detail. |
| Result detail | `pages/PositionDetailPage.tsx` | ResultDetail via useResultDetail | Summary card, evidence, review actions, review history, technical metadata; isDeleted = reviewStatus === 'INVALID'. |
| Evidence preview | `ResultEvidencePanel.tsx` | ResultDetail, getReferenceImageFileUrl, useEvidenceImageLoad | Primary/supporting hierarchy; differentiated error messages (not_found, forbidden, heic_preview_unavailable, network). |

### 1.6 API client

| File | Role | Notes |
|------|------|--------|
| `frontend/src/api/client.ts` | All v3 GET/POST calls | getAislePositions → PositionListResponse; getPositionDetail → PositionDetailResponse; getExecutionLog → ExecutionLogResponse; submitReviewAction; getReferenceImageFileUrl(jobId optional for HEIC); fetchEvidenceImage for blob + error kind. |

---

## 2. Frontend types aligned to final backend model

### 2.1 Jobs

- **Job status**: Frontend `JobStatus` and `getJobStatusLabel` / `getJobStatusColor` cover queued, running, cancel_requested, canceled, timed_out, succeeded, failed. No flattening of cancel_requested into running.
- **Latest job**: `AisleJobSummary` / `JobSummary` use `status: JobStatus | string`; API returns snake_case status. Helpers normalize for display.
- **Execution log**: `ExecutionLogResponse.events` is array; empty when missing/invalid (best-effort). UI shows empty state message; no assumption that empty = no stages ran.

### 2.2 Results / positions

- **qty**: Backend required; frontend `PositionSummary.qty: number` and mapper `resolvedQty` / `systemQty` reflect corrected_quantity ?? qty and raw qty.
- **corrected_quantity**: Optional; frontend `correctedQty: number | null`; detail shows "Manual override applied" when set.
- **qtySource**: Backend `detected` | `inferred` | `consolidated`; frontend preserves and displays as count origin; mapper default `'detected'` only when backend omits (compatibility).
- **qtyInferenceReason**, **qtyResolved**: Optional; frontend types allow null; displayed when present.
- **needs_review**: Boolean; drives NEEDS_REVIEW when status === 'detected'; frontend does not invent a review-reason field.
- **Review history**: `ReviewHistoryItem` with beforeJson/afterJson; summary built in ResultReviewHistory (with fallbacks for confirm/delete when payloads partial).
- **Traceability**: API lowercase; frontend visible model uppercase; TraceabilityChip uses mapped value.

### 2.3 Evidence / artifact preview

- **Evidence**: `EvidenceSummary` (API) → `ResultEvidence` (role PRIMARY/SUPPORTING from is_primary). source_asset_id, storage_path; imageUrl/thumbnailUrl set by UI/context.
- **Source image preview**: getReferenceImageFileUrl(inventoryId, aisleId, assetId, jobId?). jobId used for HEIC normalized preview; missing artifact → 404; useEvidenceImageLoad differentiates not_found, forbidden, heic_preview_unavailable, network.
- **Degradation**: "No evidence available", "Primary evidence recorded. Image preview is not available", "Source image is no longer available", "Preview is not available for this image" — consistent with backend best-effort artifact behavior.

---

## 3. Local fallback classification

### 3.1 Kept (necessary and conservative)

| Location | Fallback | Reason |
|----------|----------|--------|
| `positionToResult.ts` | `has_evidence`: fallback to `primary_evidence_id != null` when `has_evidence` not boolean | Backend guarantees has_evidence in v3.2.5 Block 4; fallback for transitional payloads only. |
| `positionToResult.ts` | `sourceImageId` / `sourceFileName`: fallback to getSummaryString(detected_summary_json) when typed field missing | POSITION_RESULT_CONTRACT: typed fields canonical; detected_summary_json compatibility for historical/partial. |
| `positionToResult.ts` | `qtySource: p.qtySource ?? 'detected'` | Backend sends qtySource; null/undefined only in legacy payloads. |
| `mapTraceabilityToVisible` | Unknown/missing → 'UNVALIDATED' | Safe default; backend sends valid | missing | invalid | unvalidated. |
| `mapPositionStatusToReviewStatus` | Unknown status → 'DETECTED' | Safe default; backend sends detected | reviewed | corrected | deleted. |
| `ResultReviewHistory` getChangeSummary | Fallback text "Status confirmed" / "Result removed" when before/after partial for confirm/delete_position | Partial payloads possible historically; avoids blank secondary text. |
| `ResultEvidencePanel` | "Primary evidence recorded. Image preview is not available" when canShowImage false but has evidence | Artifact missing or no source_image_id; honest degradation. |
| `useEvidenceImageLoad` | Differentiated error kinds and messages | Aligns with backend 404/403 and HEIC preview unavailability. |

### 3.2 Reduced (narrow where contract is stronger)

| Location | Current | Proposed |
|----------|---------|----------|
| `PositionSummary` (API type) | `has_evidence: boolean` with comment "v3.2.5 Block 4: guaranteed" | Keep; mapper fallback already documented as transitional only. No change needed if backend always sends. |
| List quantity display | `displayQty(r)`: resolvedQty ?? detectedQty, then NaN/negative check | Already aligned to visible qty = corrected ?? qty; only reduce if we ever showed something else (e.g. raw qty when corrected present). **No change.** |

### 3.3 Removed or not added

- **Invented review reason**: No frontend-only enum or heuristic for "why in review"; REVIEW_OPERATIONAL_CONSISTENCY defers this. UI surfaces needs_review, status, qtySource, confidence, traceability only.
- **Overriding typed fields with detected_summary_json**: Mapper already uses typed first; fallback only when typed missing. No change.

---

## 4. Final semantics (summary)

### 4.1 Job states

- **Display**: getJobStatusLabel / getJobStatusColor for all seven statuses; cancel_requested and canceled are distinct (warning chip).
- **Process button**: Disabled when aisle status is queued or processing (not by job status directly; aisle status reflects active job).
- **Cancel job**: Not exposed in UI in Phase 8; job state is read-only for operator. Deferred: dedicated Cancel button if product requires it.
- **Execution log**: Best-effort; empty events possible; message explains "job may not have started or the log file is not available."

### 4.2 Result states

- **Visible quantity**: Always corrected_quantity ?? qty (list and detail).
- **System quantity**: Shown on detail when corrected_quantity is set; from backend qty.
- **Count origin**: qtySource (detected | inferred | consolidated) + qtyInferenceReason when inferred; "Manual override applied" when corrected_quantity set.
- **Review status**: NEEDS_REVIEW when needs_review && status === 'detected'; CONFIRMED when reviewed/corrected; INVALID when deleted. No invented reason.

### 4.3 Review history

- **Change summary**: From before_json/after_json for update_quantity, update_sku; status change for confirm/delete; fallbacks "Status confirmed", "Result removed" when partial.
- **After action**: List/detail reread same API; same visible model; no separate "optimistic" path that diverges from backend.

### 4.4 Artifact / evidence preview

- **No evidence**: "No evidence available for this result."
- **Evidence but no source image**: "Primary evidence recorded. Image preview is not available for this result."
- **404**: "Source image is no longer available."
- **HEIC**: "Preview is not available for this image."
- **403/network**: Distinct messages. No generic "something went wrong" that hides 404 vs 403.

---

## 5. Historical-read interpretation rules

- **Same visual model**: List and detail use the same ResultSummary/ResultDetail mapping and same rules (visible qty = corrected ?? qty, count origin, review status). Old data does not activate a different code path.
- **Missing traceability**: Typed source_image_id / traceability_status may be null; fallback to detected_summary_json when present; otherwise null and UI shows "Image preview is not available" or equivalent.
- **Missing execution log**: events: [] and empty state message; job status still from DB.
- **Partial review history**: before_json/after_json may be empty or partial; fallback summary text for confirm/delete; update_quantity/update_sku show "—" when payload missing.
- **Positions with no evidence**: has_evidence false; hasEvidence in visible model; UI shows "No evidence available."

---

## 6. Known deferred frontend limitations

- **Cancel job**: No Cancel button in inventory detail; job status is display-only. Add when product requires operator-initiated cancel.
- **Review reason**: No dedicated needsReviewReason; operator infers from status, qtySource, traceability, confidence (documented in REVIEW_OPERATIONAL_CONSISTENCY).
- **MISSING / NOT_COUNTABLE**: In ReviewStatus type but not produced by mapper; reserved for future backend/decision layer.
- **Full audit explorer**: Only concise change summary from before/after; raw JSON not shown. Full forensic view deferred.
- **List scroll/order preservation**: Returning from detail restores filter only; scroll position and order not preserved.

---

## 7. Phase 8 implementation notes

- **First block (type alignment)**: `PositionDetailResponse.review_actions` was made required (`review_actions: ReviewActionSummary[]`) to match backend contract (backend always sends array). Mapper keeps `?? []` for runtime resilience against transitional or proxy responses.

---

## 8. Phase 8 Block 2 — Fallback audit and hardening

### 8.1 Fallback inventory (active semantic fallbacks)

| Location | Fallback | Affects |
|----------|----------|--------|
| `positionToResult.ts` | `qtySource ?? 'detected'` (list + detail) | Count-origin display; KPI/filters do not use qtySource directly. |
| `positionToResult.ts` | `has_evidence` when not boolean → `Boolean(primary_evidence_id)` | hasEvidence in ResultSummary/ResultDetail; KPI withEvidence, filters, evidence column. |
| `positionToResult.ts` | `sourceImageId` / `sourceFileName`: typed first, then `getSummaryString(detected_summary_json, …)` | Evidence preview, primary evidence label, image URL. |
| `positionToResult.ts` | `evidences ?? []`, `review_actions ?? []` | Detail evidence list and review history. |
| `positionToResult.ts` | `mapTraceabilityToVisible`: unknown/missing → `'UNVALIDATED'` | Traceability chip; KPI valid/non-valid traceability. |
| `positionToResult.ts` | `mapPositionStatusToReviewStatus`: unknown status → `'DETECTED'` | Review status chip; filters. |
| `ResultReviewHistory.tsx` | getChangeSummary: confirm/delete when before/after partial → "Status confirmed" / "Result removed" | Secondary text in history list. |
| `ResultEvidencePanel` | canShowImage false but has evidence → "Primary evidence recorded. Image preview is not available" | Honest degradation. |
| `useEvidenceImageLoad` | Differentiated error kinds (not_found, forbidden, heic_preview_unavailable, network) | Evidence image error message. |
| `ResultsTable` displayQty | `resolvedQty ?? detectedQty`, then NaN/negative → '—' | List quantity column. |
| KPI / filters | needsReview, traceabilityStatus, detectedQty === 0, hasEvidence, confidence | Counts and filter results. |

### 8.2 Classification (Block 2)

| Fallback | Classification | Reason |
|----------|----------------|--------|
| `qtySource ?? 'detected'` | **Keep** | Historical payloads (pre–v3.2.2 or proxy) may omit qtySource; backend now always sends it. Removing would break legacy reads. Documented in code as historical-only. |
| `has_evidence` not boolean → primary_evidence_id | **Reduce** | Classified as transitional/historical only; canonical value is has_evidence when boolean. Explicit comment added; test proves explicit false is not overridden. |
| source image/filename: typed first, then detected_summary_json | **Keep** | Typed fields are canonical; blob fallback only when typed absent (historical). Existing tests prove typed wins. |
| traceability unknown → UNVALIDATED | **Document-only** | Backend sends valid\|missing\|invalid\|unvalidated; default is safe and documented. |
| review status unknown → DETECTED | **Document-only** | Backend sends detected\|reviewed\|corrected\|deleted; default is safe and documented. |
| review history confirm/delete fallback text | **Keep** | Partial before/after possible historically; avoids blank secondary text. |
| evidences/review_actions ?? [] | **Keep** | Runtime resilience; review_actions type is now required. |
| displayQty resolvedQty ?? detectedQty | **Keep** | Aligned to visible qty rule; no change. |
| KPI/filters using ResultSummary fields | **Keep** | They use mapper output; no legacy proxies. |

### 8.3 Implemented changes (Block 2)

- **positionToResult.ts**: Added explicit comments on each fallback (traceability/review status: document-only; has_evidence: reduce, transitional; qtySource: keep, historical-only; source image: canonical first, fallback historical). No behavior change; intent clarified.
- **Tests**: (1) Fixed "handles empty evidences and review_actions" to include required `review_actions: []`. (2) Case 4: qtySource omitted (historical payload) → fallback to 'detected'. (3) Case 5: has_evidence explicitly false is not overridden by primary_evidence_id (canonical wins).
- **No removals**: All fallbacks retained; scope narrowed only by documentation and tests proving canonical behavior.

### 8.4 Remaining transitional fallbacks (after Block 2)

- **qtySource ?? 'detected'**: Kept for historical payloads; backend now always sends qtySource. Revisit if/when legacy API is fully retired.
- **has_evidence** when not boolean: Fallback to primary_evidence_id; documented as transitional. Backend guarantees has_evidence in active v3.
- **source_image_id / source_image_original_filename**: Fallback to detected_summary_json when typed absent; kept for historical/partial reads. Typed fields remain canonical.
- **evidences ?? []**, **review_actions ?? []**: Kept for runtime resilience; review_actions type is required.
- **Traceability/status defaults** (UNVALIDATED, DETECTED): Document-only; no narrowing.
- **Review history** "Status confirmed" / "Result removed": Kept for partial payloads.
