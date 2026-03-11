# Épica 7 — Implementation Note

## 1. Backlog interpretation

Épica 7 formalizes the result consultation layer: list positions (with product summary), detail position. Mandatory: `sku` and `detected_quantity` in list response as first-class fields.

## 2. Current state

List/detail endpoints and use cases exist. List returns PositionSummaryResponse with detected_summary_json. Frontend parses that JSON for SKU and quantity.

## 3. Épica 6 already done

Persistence (positions, product_records, evidences); mapper writes detected_summary_json; list/detail endpoints and pages.

## 4. Gaps

Explicit sku/detected_quantity on list response; backend tests for list/detail and summary fields; frontend types and table using first-class fields.

## 5. Source of sku / detected_quantity

ProductRecord has them. Position.detected_summary_json has internal_code, final_quantity, product_label_quantity. For list we derive from detected_summary_json in API layer (no N+1).

## 6–9. Files

Backend: position_schemas.py (add sku, detected_quantity), inventories_v3.py (derive in _position_to_summary), tests. Frontend: types.ts (add fields), AislePositionsPage (use p.sku / p.detected_quantity with fallback).

## 10–11. Design

Backend: Optional sku/detected_quantity on PositionSummaryResponse; derive from position.detected_summary_json in route. Frontend: Prefer p.sku and p.detected_quantity; fallback to existing helpers.

## 12. Risks

None. Additive; backward compatible.
