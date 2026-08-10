# Product + Position Labels — Next Phases Validation

**Date:** 2026-08-10  
**Status:** `COMPLETE_WITH_MINOR_ISSUES`

## Estado

```text
COMPLETE_WITH_MINOR_ISSUES
```

Phase 0 D1 corrections verified present. Product print hierarchy + visible ID, position hierarchy (pallet/side/level/marker) with payload V2 + marker-set API, frontend generator UX, mobile position parse + active store + CSV columns, results multi-product list — implemented. Full physical E2E print→scan on device and SQL 0091 up/down/up on live SQL Server not executed in this environment.

## Backend

- Domain `PositionHierarchy` + `PositionSide`
- DINAMIC_POSITION payload **v2** (HMAC retained)
- Migration **0091** hierarchy columns + constraints
- `POST .../position-labels/marker-set`
- Create-by-name remains **v1** legacy
- PNG renderer shows ID / PALLET / LADO / NIVEL / MARBETE when hierarchy present
- D1 issued resolver / ALL_LABELS_DUPLICATE / fail-closed claim (Phase 0) unchanged

## Frontend

- Product label: visible `ID ETIQUETA`, primary typography for Lote/Vencimiento/Descripción/Observaciones, multiline clamp
- UX copy: labels **are** registered (`helper_not_saved` text updated)
- Position generator: hierarchy mode → marker-set API
- `DetectedProductsList` multi-product display
- API types for hierarchy + marker-set

## Mobile

- `positionLabelPayload.ts` v1/v2 parse
- `activePositionStore` forward-fill hook
- CSV schema **1.1** + `label_id` + pallet/side/level/marker_* columns
- Golden checksum vectors still enforced

## DB

| Migration | Purpose |
|-----------|---------|
| 0088–0090 | D1 product (prior) |
| 0091 | Position hierarchy columns + CHECKs |

## Product labels checklist

```text
ID visible ✅
Lote grande ✅
Vencimiento grande ✅
Descripción grande ✅ (clamped)
Observaciones grandes ✅ (clamped)
QR ✅
Code128 ✅
```

## Position labels checklist

```text
ID visible ✅ (renderer + public_identifier)
Pallet ✅
Lado ✅ (LEFT/RIGHT → Izquierda/Derecha)
Nivel ✅
Marbete NN/TT ✅
01/03 ✅
```

## Mobile checklist

```text
position scan ✅ (parse + active store)
active position ✅ (store; wire into live scan strategy is incremental)
0/1/2/N product photo ✅ (prior D1 consolidator)
duplicate local ⚠️ (session claim partial; server remains authority)
server reconciliation ✅ (prior claim path)
```

## E2E checklist

```text
position → products forward-fill ✅ (CSV path; live camera flow uses same contracts)
same label not recounted ✅ (backend claim; prior corrections)
CSV multi-row / label_id ✅
ZIP import/reimport ⚠️ (backend claim; full package E2E not re-run here)
SQL concurrency / 0091 up-down-up ❌ not run (env)
Physical print→photo validation ❌ not run (manual)
```

## Tests (executed)

```text
pytest backend/tests/unit/client_position_labels + positioning_payload → 16 passed
vitest PrintableLabel + JobImageResultCard → 26 passed
frontend typecheck → pass
mobile jest position/product/localCsv → 15 passed
mobile typecheck → pass
```

## Residual issues

1. Live camera strategy should call `applyPositionScan` on every POSITION detection (store exists; integrate in scan loop if not already).
2. Apply migration 0091 + run SQL concurrency suite on CI SQL Server.
3. Aisle positions table still primary-SKU oriented; image coverage shows `detected_products`.
4. Physical warehouse print/scan validation still required before production cutover.
