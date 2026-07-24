# Mobile CODE_SCAN Phase 3 — Metrics Report

Only measured values are listed. No invented precision.

| Escenario | Imágenes | Resueltas local | Match código | Match cantidad | Tiempo p50 | Tiempo p95 |
| --------- | -------: | --------------: | -----------: | -------------: | ---------: | ---------: |
| _(none measured)_ | — | — | — | — | — | — |

## Device validation pending

Enable flags on a release build:

```bash
DINAMIC_FLAG_LOCAL_CODE_SCAN=1
DINAMIC_FLAG_LOCAL_CODE_SCAN_COMPARE=1
DINAMIC_FLAG_LOCAL_CODE_SCAN_DEBUG=1
```

Then run the Samsung S10+ matrix from the Phase 3 plan (§31) and fill this table from observability exports (`local_scan_ms`, compare rates).
