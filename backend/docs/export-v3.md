# v3 inventory export (operational)

## Legacy exports (unchanged contract)

- `GET /api/v3/inventories/{inventory_id}/export` — flat operational rows, all aisles, English snake_case columns.
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` — same columns, one aisle; default `profile=legacy`.
- `?technical=true` — technical snapshot columns (unchanged).

The web UI does **not** expose legacy CSV download. Legacy remains available via API for integrators and support.

## Additive business exports

- `GET …/aisles/{aisle_id}/export?profile=business` — Spanish headers, readable columns, rollup metadata columns (UI default for aisle export).
- `GET …/inventories/{inventory_id}/export/summary?level=inventory|aisles` — rollup summary CSV.
- `GET …/inventories/{inventory_id}/export/package` — ZIP with `inventory_summary.csv`, `aisles_summary.csv`, and `aisles/aisle_*_operational.csv`.

ZIP and summary exports build all files from **one** `collect_inventory` snapshot so totals and aisle rows stay consistent.

## Totals

`ExportQuantityRollupService` centralizes counted quantity and inclusion rules (`final_quantity`, deleted excluded from totals, traceability-invalid excluded from totals by default).

Business operational CSV may **include** deleted rows for auditability (`Incluido en totales = no`, `Motivo de exclusión = Eliminada`). Legacy flat export continues to **omit** deleted rows.

## Cost fields

| Export | Cost behavior |
|--------|----------------|
| Summary (`Costo del pasillo`, `Costo total del inventario`) | Uses persisted operational job `llm_cost_snapshot.computed_cost.total_cost` when available; empty otherwise. Inventory total is the sum of aisle job costs when numeric. |
| Business operational (`Costo unitario`, `Costo total de línea`) | Reserved for future unit/line pricing. Always empty today — job cost is **not** distributed across rows. |

No production unit pricing is invented.
