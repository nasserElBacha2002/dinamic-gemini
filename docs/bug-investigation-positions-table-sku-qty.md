# Bug Investigation — Positions table missing SKU and detected quantity

## Symptom

The aisle positions table did not show SKU or detected quantity columns. Data was only visible on the position detail page.

## Expected Behavior

Table must display SKU and detected quantity as first-class columns, with safe fallback "—" when missing.

## Root Cause

Data exists in the list response in `position.detected_summary_json` (internal_code, final_quantity/product_label_quantity). The table had no columns reading from it.

## Fix Applied

- Added two columns: SKU, Detected qty.
- Added helpers `getPositionSku(p)` and `getPositionDetectedQuantity(p)` reading from `detected_summary_json` with "—" fallback.
- No backend change; no type change required (PositionSummary already has detected_summary_json).
