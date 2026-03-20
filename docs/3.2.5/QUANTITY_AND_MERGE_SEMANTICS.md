# Quantity and Merge Semantics (v3.2.5)

## 1) Authoritative quantity vs merge artifact

Dinamic Inventory now treats these as separate concepts:

- **Authoritative quantity**: primary quantity used for inventory and review.
- **Merge/consolidation quantity**: post-process artifact to group repeated SKU labels.

Merge quantity is not the default source of truth for `ProductRecord.detected_quantity`.

## 2) Quantity source priority

Target business priority:

1. manual review (`corrected_quantity`)
2. explicit label quantity
3. extracted quantity (OCR/LLM)
4. fallback inference
5. unknown/unresolved

## 3) Why merge moved out of main authoritative write path

In v3.2.3, consolidation could project `len(group)` into authoritative product quantity,
which could overwrite explicit label values (e.g. 36 -> 1).  
In v3.2.5, the persist flow keeps authoritative quantity and runs recompute without
authoritative overwrite.

## 4) Merge execution model

- Main aisle processing persists positions/products/evidence first.
- Merge runs as explicit post-process:
  - `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge`
  - `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge-results`
- Merge results remain queryable and auditable as separate artifacts.
- `product_records_updated` is kept for backward compatibility in the merge response;
  in `artifact_only` mode it should remain `0`.

## 4.1 Quantity source currently emitted

The active backend now emits truthful provenance values currently supported by persisted data:

- `label_explicit`: explicit parsed quantity from label-oriented fields (`final_quantity` / `product_label_quantity`) when valid.
- `inferred`: fallback inference path (no explicit quantity).
- `merge_inferred`: quantity derived from merge artifact projection when allowed.
- `manual_review`: quantity controlled by manual correction.
- `detected`: generic detected path when explicit classification is not available.
- `unknown`: unresolved/legacy unknown source.

Values such as `ocr` and `llm_extracted` are not emitted yet because current persisted
data does not reliably separate those origins.

## 5) Frontend behavior

- Main results list/detail continues to show authoritative quantity contract (`qty`, `qtySource`).
- Merge is an optional explicit action (`Run Merge`) and should be interpreted as
  consolidation metadata, not automatic replacement of authoritative quantity.

