# Position / Result Contract (Release 3.2.5 Phase 5)

**Scope**: v3 positions endpoints and the frontend Result model.
This document defines stable semantics for quantities, count origin, review state, evidence, and nullability.

---

## 1. Active endpoints and DTOs

### Backend endpoints
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions`
  - response: `PositionListResponse { positions: PositionSummaryResponse[] }`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`
  - response: `PositionDetailResponse { position, evidences, review_actions }`

### Backend DTOs
Source: `backend/src/api/schemas/position_schemas.py`

- `PositionSummaryResponse` (used in both list and detail)
- `EvidenceResponse`
- `ReviewActionResponse`
- `ReviewActionRequest`

### Backend mapping and data sources
- DTO mapper: `backend/src/api/routes/v3/shared.py` `position_to_summary`
- List route: `backend/src/api/routes/v3/positions.py` `list_aisle_positions`
  - selects a deterministic “display primary” ProductRecord (first by `(created_at, id)`) to supply `corrected_quantity` and qty provenance
- Detail route: `backend/src/api/routes/v3/positions.py` `get_position_detail`
  - uses the same deterministic “display primary” and the same `position_to_summary` mapper

### Frontend visible model
Source: `frontend/src/features/results/types.ts`

- `ResultSummary`
- `ResultDetail`

Mapping source: `frontend/src/features/results/mappers/positionToResult.ts`

---

## 2. Quantity fields and authoritative semantics

### 2.1 Fields
- `qty` (required): backend-resolved **system quantity** for the position/result **before manual override**.
- `corrected_quantity` (nullable): operator/manual override quantity.
- `detected_quantity` (nullable): convenience/display value derived from summary blobs; not guaranteed to represent raw model output.
- `qtySource`: provenance of `qty` (see §3).
- `qtyInferenceReason` (nullable): explanation when `qtySource == "inferred"`.
- `qtyResolved` (nullable): when true/false, indicates `qty` comes from an explicit resolution decision; null indicates legacy/compatibility path.
  - **Intentional**: consolidated rows are treated as explicit resolutions and should emit `qtyResolved=true`.

### 2.2 Visible quantity used by the UI (stable rule)
The UI MUST treat the visible quantity as:

`final_visible_qty = corrected_quantity ?? qty`

This rule is used consistently for both list and detail.

### 2.3 Manual correction
If `corrected_quantity` is non-null, it is the authoritative visible quantity and represents a manual/operator override.
In that case, `qty` remains the system-resolved quantity and is retained for audit/debugging.

---

## 3. Count origin / provenance

### 3.1 Purpose
Count origin must allow an operator/engineer to answer:
- was the system quantity detected, inferred, consolidated, or manually corrected?

### 3.2 System quantity provenance (`qtySource`)
`qtySource` describes the origin of `qty` (system-resolved quantity), not the final visible quantity after correction.

Allowed values:
- `detected`: system quantity comes from explicit detected quantity.
- `inferred`: system quantity is inferred by a rule; `qtyInferenceReason` should be non-null.
- `consolidated`: system quantity results from consolidation/merge across multiple underlying positions/entities (e.g. SKU-level aggregation).

### 3.3 Final visible quantity provenance
Final visible quantity provenance is derived as:
- `corrected` when `corrected_quantity != null`
- otherwise `qtySource`

Phase 5 does not introduce a dedicated `finalQtyOrigin` field; the above rule defines the semantics.

---

## 4. Review state and `needs_review`

### 4.1 Fields
- `needs_review` (boolean): indicates the position requires operator attention.
- `status` (string): backend position status (domain: `detected`, `reviewed`, `corrected`, `deleted`).

### 4.2 Visible review status (frontend)
The frontend maps `(status, needs_review)` to visible review status:
- NEEDS_REVIEW when `needs_review == true` and `status == "detected"`
- CONFIRMED when `status in {"reviewed","corrected"}`
- INVALID when `status == "deleted"`
- DETECTED otherwise

### 4.3 Phase 5 note: needs_review reason
In the current contract, `needs_review` is a boolean without an explicit reason field.
It can be partially explained by existing fields (e.g. status, evidence presence, qty inference, traceability), but the repo does not expose a stable `needsReviewReason` enum yet.
In the current visible model, `needs_review` only changes the UI review status when `status == "detected"`. For `status in {"reviewed","corrected"}`, the UI is always `CONFIRMED` regardless of `needs_review`.
If a reason field is introduced later, it must be small, stable, and conservative (UNKNOWN when evidence is insufficient).

### 4.4 Phase 6 note: needs_review and corrected state after manual actions
After any successful manual review action (`confirm`, `update_quantity`, `update_sku`, `delete_position`), the backend sets `needs_review = false`. Reread (list and detail) therefore shows coherent review state and corrected/deleted semantics without contradicting filters or KPIs that use `needs_review`. See `docs/3.2.5/REVIEW_OPERATIONAL_CONSISTENCY.md` for full reread guarantees.

---

## 5. Evidence and traceability

### 5.1 EvidenceResponse
`EvidenceResponse` represents traceability artifacts (crops/media) for a position.
It does not determine `qty`; it supports explainability and review.

### 5.2 Traceability fields on position summary/detail
- `source_image_id`, `traceability_status`, `source_image_original_filename` are optional.
- Typed fields are canonical when present.
- `detected_summary_json` may contain compatibility copies; these must not override typed values.

---

## 6. Nullability rules

- `qty`: required, always present.
- `corrected_quantity`: null means “no manual override”.
- `qtyInferenceReason`: should be null unless `qtySource == "inferred"`.
- `qtyResolved`: null indicates legacy/compatibility path or missing explicit resolution info; true/false indicates explicit resolution.
- `detected_summary_json`: optional; treated as compatibility/debug carrier, not the primary contract.
- `source_image_*`: optional; may be missing for historical runs or when artifacts are unavailable.

---

## 7. Compatibility/debug fields (do not override authoritative semantics)

- `detected_summary_json`: retained for historical payloads and for compatibility/debug enrichment.
  - It must not override the authoritative semantics for `qty` provenance (`qtySource`) or typed traceability fields when those are available.
- Frontend fallbacks (e.g. typed source-image fallback to detected_summary_json) are defensive and must not override explicit backend values.

---

## 8. Decisions implemented in Phase 5 (Block 1)

- `qtySource` was widened to include `consolidated`.
- Consolidated/aggregated rows now emit `qtySource = "consolidated"` instead of collapsing to `"detected"`.
- Frontend raw types and visible result model preserve `"consolidated"` through mapping.
- Visible quantity rule remains: `corrected_quantity ?? qty`.

---

## 9. Deferred items

- Explicit per-item “final visible qty origin” field (e.g. `finalQtyOrigin`) is deferred; current semantics are defined in §3.3.
- Explicit `needs_review` reason field is deferred until the backend can expose a stable, non-heuristic basis.
- Additional artifact references (“artifacts supporting this result”) remain deferred.

---
