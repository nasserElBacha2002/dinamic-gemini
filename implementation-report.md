# Implementation report — Physical product labels (D1, 0..N per photo)

## Executive summary

Estado: **COMPLETE_WITH_MINOR_ISSUES**

Implemented Dinamic physical product labels with unique `label_id`, read checksum (not HMAC), scanner/pipeline **0..N products per image**, inventory-scoped dedupe with DB uniqueness, mint API, multi-row CSV fields, and shared checksum vectors across backend/frontend/mobile.

Minor gaps: aisle results **table UI** still surfaces the primary product per position (API/CSV expose all products); local CSV import schema v1 still lacks optional `label_id` column; ZIP import dedupe relies on existing counted-label claim path once rows carry `label_id`.

## Qué se implementó

Flujo final:

```text
POSITION label → active position (unchanged; HMAC preserved)
IMAGE → RawCode[] (rotations merged)
     → classify D1 PRODUCT vs legacy PIPE/DI1 vs OTHER
     → validate label_id + checksum
     → dedupe by label_id (intra-image)
     → ProductResult[0..N]
     → persist N ProductRecords on one Position
     → claim UNIQUE(inventory_id, label_id)
     → forward-fill shelf via existing reconciliation
     → export one CSV row per product when label_id present
```

## Arquitectura final

| Concern | Implementation |
| --- | --- |
| Format | `D1\|<label_id>\|<internal_code>\|<quantity>\|<checksum>` |
| Checksum | Weighted Mod-36 over canonical body (read integrity only) |
| Identity | `label_id` (Crockford-like, length 10); never recycle via `issued_product_labels` |
| Count-once | `inventory_counted_product_labels` UNIQUE(inventory_id, label_id) + `try_claim` |
| POSITION | Unchanged; multi VALID positions still conflict/review |
| Legacy | PIPE / DI1 / PLAIN still countable ≤1 when no D1 present |

## Archivos modificados

| Archivo | Cambio |
| --- | --- |
| `backend/src/domain/product_labels/format.py` | D1 build/parse/checksum + ID generation |
| `contracts/product-labels/v1/checksum-vectors.json` | Shared golden vectors |
| `backend/.../code_detection_consolidator.py` | 0..N D1 products; intra-image dedupe |
| `backend/.../code_scan_processing_strategy.py` | Multi product_results; rotation merge |
| `backend/.../processing_result_persister.py` | N ProductRecords + inventory claim |
| `backend/.../0088_product_label_identity.sql` | issued + counted tables; product_records.label_id |
| `backend/.../issue_product_labels.py` + API | Mint unique stickers |
| `backend/.../export_inventory_results.py` | Multi-row when label_id present; CSV columns |
| `backend/.../list_job_image_results.py` | `products` / `detected_products` |
| `frontend/.../productLabelPayload.ts` | Shared D1 algorithm |
| `frontend/.../LabelGeneratorDialog.tsx` | Mint on print → D1 payloads |
| `mobile/.../productLabelFormat.ts` + consolidator | 0..N + checksum |

## Migraciones

`0088_product_label_identity.sql` (auto-picked):

- `issued_product_labels` (global UNIQUE label_id)
- `inventory_counted_product_labels` UNIQUE(inventory_id, label_id)
- `product_records.label_id` nullable + filtered index

Rollback: `0088_product_label_identity.down.sql`

## Compatibilidad legacy

| Format | Counted? | label_id |
| --- | --- | --- |
| D1 | Yes (0..N) | Required |
| PIPE `code\|qty` | Yes (≤1 when no D1) | None (not invented) |
| DI1 | Yes (≤1) | None |
| Plain / external EAN | No Dinamic item when not our format / no qty | — |

## Deduplicación

- Intra-image: by `label_id`
- Cross-image / concurrency: UNIQUE(inventory_id, label_id) + insert claim (IntegrityError → skip)
- Not by SKU, not by checksum

## Concurrencia / idempotencia

- Same photo retry: coverage uniqueness for `(job_id, source_asset_id)`
- Same label_id another photo: claim returns false → no second counted row
- Workers racing: DB unique constraint wins one insert

## Tests

| Command | Result |
| --- | --- |
| `pytest` product_labels + consolidator multi + claim + issue + strategy | **32 passed** |
| `frontend` productLabelPayload + LabelGeneratorDialog | **passed** |
| `frontend` typecheck | **passed** |
| `mobile` test:core productLabelMulti + labelPayloadContracts | **passed** |
| `mobile` typecheck:core | **passed** |

## Casos validados

```text
0 productos por foto ✅
1 producto por foto ✅
2 productos por foto ✅
N productos por foto ✅ (5)
duplicado intra-foto ✅
duplicado entre fotos ✅ (claim unit)
mismo SKU con distintos IDs ✅
checksum inválido ✅
barcode externo ✅ (no D1 items)
posición forward-fill ✅ (unchanged reconciler; multi products on position)
retry ✅ (coverage idempotency preserved)
concurrencia ✅ (claim UNIQUE memory + SQL IntegrityError path)
CSV multi-row ✅ (export path + columns)
ZIP/import ⚠️ (export package uses same row builder; import schema label_id follow-up)
legacy ✅ (PIPE path)
```

## Riesgos restantes

1. Aisle results UI still primary-SKU oriented — operators need CSV/`detected_products` for full multi-label visibility until table UI is extended.
2. Local CSV v1 import does not yet accept `label_id` → re-import may not claim D1 identity.
3. Preview barcodes before print still use legacy PIPE until mint; printed copies use D1 after mint.
4. Migration 0088 must be applied in each environment before SQL claim/persist.
