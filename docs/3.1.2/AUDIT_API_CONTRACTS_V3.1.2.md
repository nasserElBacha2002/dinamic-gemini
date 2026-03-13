# AUDIT_API_CONTRACTS_V3.1.2.md

## 1. Summary

This document reports the backend ↔ frontend contract audit for Dinamic Inventory v3.1.2. It maps key endpoints to response shapes and to actual frontend consumption to identify unused fields, duplication, and over-fetching.

## 2. Scope

- **Included:** v3 endpoints consumed by `frontend/src/api/client.ts` and their Pydantic/response schemas; frontend types in `api/types/responses.ts` and usage in pages/features/hooks.
- **Excluded:** v1 endpoints except `getJobEntities` (single v1 consumer); no changes to backend or frontend.

## 3. Findings

### 3.1 Key endpoints and response shapes

| Endpoint | Backend schema (main) | Frontend type | Consumed by |
|----------|------------------------|---------------|-------------|
| GET /api/v3/inventories | List[InventoryResponse] | Inventory[] | useInventories, InventoriesList, InventoryDetail |
| GET /api/v3/inventories/{id} | InventoryResponse | Inventory | useInventories (getInventory) |
| GET /api/v3/inventories/{id}/metrics | InventoryMetricsResponse | InventoryMetrics | useAisles (getInventoryMetrics), InventoryDetail |
| GET /api/v3/inventories/{id}/aisles | List[AisleResponse] | Aisle[] | useAisles, InventoryDetail |
| GET .../aisles/{aid}/status | AisleStatusResponse | AisleStatusResponse | getAisleStatus (polling), UI status |
| GET .../positions | PositionListResponse | PositionListResponse | usePositions, AislePositionsPage |
| GET .../positions/{pid} | PositionDetailResponse | PositionDetailResponse | usePositions (detail), PositionDetailPage |
| GET .../assets | List[SourceAssetResponse] | SourceAssetSummary[] | getAisleAssets, upload/asset list |
| GET .../assets/{id}/file | FileResponse | URL (getReferenceImageFileUrl) | ResultEvidencePanel, img src |
| GET .../jobs/{jid}/execution-log | ExecutionLogResponse | ExecutionLogResponse | ExecutionLogPanel |

Backend response field names align with frontend types (snake_case; Pydantic serialization).

### 3.2 Field-level usage (positions and detail)

**PositionSummary / PositionListResponse.positions:**

- Backend: id, aisle_id, status, confidence, needs_review, primary_evidence_id, created_at, updated_at, detected_summary_json, sku, detected_quantity, corrected_quantity, source_image_id, traceability_status, has_evidence, source_image_original_filename.
- Frontend (results feature): Mappers and selectors use id, status, confidence, sku, detected_quantity, corrected_quantity, source_image_id, traceability_status, has_evidence, source_image_original_filename, created_at, updated_at. `detected_summary_json` is used for backward compatibility where summary fields are missing. **Most fields consumed.**
- **Unused / optional:** primary_evidence_id may be used only indirectly (has_evidence); aisle_id present on summary but list is per-aisle so may be redundant in list view. **Low impact.**

**PositionDetailResponse (position + evidences + review_actions):**

- position: same as summary; evidences and review_actions fully used in ResultEvidencePanel and ResultReviewActions/ResultReviewHistory.
- **Over-fetch:** If detail is always loaded after list, list and detail both carry position summary; acceptable for clarity and cache. No clear redundant nested object.

### 3.3 Inventory and aisle

- **Inventory:** id, name, status, created_at — all used. Backend may return updated_at; frontend type has created_at optional. **Aligned.**
- **Aisle:** id, inventory_id, code, status, created_at, updated_at, error_code, error_message, latest_job. Frontend uses all for list and status. **Aligned.**
- **AisleStatusResponse:** aisle + latest_job (JobSummary). Used for polling and error display. **Aligned.**

### 3.4 Metrics

- **InventoryMetricsResponse:** total_positions, total_reviewed_positions, auto_accepted_positions, corrected_positions, deleted_positions, success_rate, correction_rate, deletion_rate. Frontend (InventoryDetail, KPIs) consumes these. **All used.**

### 3.5 Execution log

- **ExecutionLogResponse.events:** ts, stage, level, message, payload. Frontend ExecutionLogPanel displays them. **Aligned.**

### 3.6 Duplicated or redundant fields

- **Position list vs detail:** Summary fields repeated in detail.position; by design for consistency. No duplicate field names within the same response.
- **Aisle in status:** Full aisle object inside AisleStatusResponse; same shape as list item. Acceptable for status view.

### 3.7 Unused fields (candidates for removal later)

- **SourceAssetSummary.storage_path:** Comment in frontend types says "not used by current UI (reserved for future evidence/media views)". **Candidate** for keeping for future use or removing from response if contract optimization is done.
- **Position summary primary_evidence_id:** Used to derive has_evidence on backend; frontend may not read it directly if has_evidence is always set. **Low impact.**

### 3.8 v1 entities response

- **GET .../entities:** entities[] (with traceability, source_image_id, source_image_original_filename, etc.) + traceability_summary. Frontend type and getJobEntities exist; exact consumer component needs confirmation. If unused, entire response is **candidate for removal** with v1 route.

## 4. Classification

| Contract area | Classification | Note |
|---------------|----------------|------|
| v3 inventories/aisles/positions/assets/status/execution-log | **Active, aligned** | Field usage matches backend |
| Position summary/detail | **Active** | Minor redundancy (list vs detail summary) |
| Metrics, execution log | **Active** | Fully consumed |
| storage_path on asset | **Optional / reserved** | Document or remove in optimization |
| v1 entities | **Unclear** | Confirm consumer before removal |

## 5. Risks

- Removing a field that appears unused but is used in a conditional or downstream transform could break UI. Recommendation: profile usage (e.g. grep + runtime) before stripping fields.
- Changing v1 entities contract without a dedicated deprecation path could break any remaining consumer.

## 6. Recommendations

- Before Stage 5 (backend optimization), run a field-usage map: for each response type, list every property access in frontend (including mappers and selectors). Then mark truly unused fields for removal or document as reserved.
- Keep summary and detail position shape consistent; if optimizing payload size, consider lighter summary DTO (e.g. omit detected_summary_json when sku/detected_quantity are present) in a later iteration.

## 7. Candidate next-stage actions

- **Stage 5:** After frontend usage map, remove or narrow unused fields (e.g. storage_path, primary_evidence_id) and update frontend types. Optionally add a "summary" variant of position list item with fewer fields.
- **Stage 2/4:** If v1 entities are removed, delete getJobEntities and related types; document in release notes.
