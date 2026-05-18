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

## Source of truth (Aisle Results UI)

Business exports and summaries use the same projection rules as the **Aisle Results** screen (`AislePositionsPage`):

- Positions loaded per aisle with `ResultContextResolver` (operational job slice, or explicit `job_id` on aisle export).
- **No SKU merge** (`consolidate_by_sku=false`), matching the UI list query.
- Quantity per row: canonical `final_display_quantity` (operator correction when set, else detected/resolved), same as API `quantity.final` / UI `resolvedQty ?? detectedQty`.
- **Counted totals** match UI `computeResultsKpi` / `isExcludedFromCountedTotals`:
  - Included: all rows except `deleted` position status (UI `reviewStatus === 'INVALID'`).
  - Traceability-invalid rows **are included** in `Total contabilizado` and `Ítems contados` (same as UI).
- Deleted rows may appear in business operational CSV for audit (`Incluido en totales = no`, `Motivo de exclusión = Eliminada`) but do not affect totals.

Inventory summary `Total contabilizado` equals the sum of per-aisle UI-style totals. Each `aisles_summary.csv` row matches the corresponding operational aisle CSV when summing rows with `Incluido en totales = sí`.

Legacy flat export still omits deleted rows and may consolidate by SKU (unchanged).

## Summary column meanings

| Column | Meaning |
|--------|---------|
| **Total contabilizado** | Sum of `Cantidad final` for rows included in totals — matches UI **TOTAL CONTABILIZADO**. |
| **Ítems contados** | Count of rows included in totals — matches UI **Ítems contados** (`ExportQuantityRollupService.valid_positions`). |
| **Total de filas exportadas** | All rows emitted in the business operational export for that scope (including audit rows excluded from totals). |
| **Filas excluidas del total** | Rows shown for audit but not included in `Total contabilizado` / `Ítems contados` (e.g. deleted). |

Operational CSV consistency:

- `count(rows where Incluido en totales = sí)` = `Ítems contados` in the matching summary row.
- `sum(Cantidad final where Incluido en totales = sí)` = `Total contabilizado` in the matching summary row.

## Cost fields

| Export | Cost behavior |
|--------|----------------|
| Summary (`Costo del pasillo`, `Costo total del inventario`) | Uses persisted operational job `llm_cost_snapshot.computed_cost.total_cost` when available; empty otherwise. Inventory total is the sum of aisle job costs when numeric. |
| Business operational (`Costo unitario`, `Costo total de línea`) | Reserved for future unit/line pricing. Always empty today — job cost is **not** distributed across rows. |

No production unit pricing is invented.
