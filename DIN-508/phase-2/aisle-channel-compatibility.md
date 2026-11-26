# DIN-508 Phase 2 — Aisle / channel compatibility

## SQL Server (read-only probe)

Source: `DIN-508/phase-2/sql-collation-probe-output.txt` (executed against local DB via `run_sql_collation_probe.py`).

| Finding | Value |
|---------|--------|
| `aisles.code` type | `VARCHAR(64)` |
| Collation | `SQL_Latin1_General_CP1_CI_AS` |
| Uniqueness | `UQ_aisles_inventory_code` on `(inventory_id, code)` |
| Case sensitivity | **Case-insensitive** (CI) for equality in SQL |
| Stored samples | All recent rows `trimmed_match=1` (no leading/trailing spaces in DB) |
| `N'a-03'` vs `N'A-03'` | Both would match same row if code were `A-03` (CI) |
| Literal padded code `N' A-03 '` | `padded_match=0` (app uses `.strip()` before persist/lookup) |

## Application vs MediaMTX paths

| Layer | Rule |
|-------|------|
| Backend lookup | `get_by_inventory_and_code` uses `code.strip()` + exact SQL equality (CI) |
| MediaMTX path | `live/{inventory_id}/{16-hex slug}` where slug = `sha256(inventory_id + NUL + canonical_upper(strip(code)))[:16]` |
| Special characters in aisle code | Allowed in SQL; **not** embedded in RTMP path (slug only) |

**Canonical rule (Phase 2 correction):** `strip()` then **uppercase** (`SQL_Latin1_General_CP1_CI_AS` case fold for admitted Latin aisle codes). `A01` and `a01` share one slug.

Example (POC env):

```
inventory=550e8400-e29b-41d4-a716-446655440001  aisle=A-03
→ live/550e8400-e29b-41d4-a716-446655440001/2d4196bc46b61307
```

**Residual:** Unicode accents are not folded in Python unless SQL would treat them as equal (see `test_channel_id.test_accent_distinct_canonical`). Inventory IDs are normalized with `uuid.UUID`. Literal SQL equivalence probes: `sql_collation_literal_equivalence.sql`.

Real inventory sample:

```
inventory=f00e01a8-1514-46a4-a5b9-711ead486509  aisle=Andes
→ live/f00e01a8-1514-46a4-a5b9-711ead486509/740c795f1c8e0d36
```

## Pre-aisle streaming

POC publishes to the derived path **without** any SQL row. Association is logical (inventory UUID + trimmed aisle code → slug). Future backend resolution can call the same `channel_id` helper before issuing credentials.

## Risks (from Phase 1, updated)

| Risk | Phase 2 status |
|------|----------------|
| R1 Collation CI vs app case-sensitive display | **Partially resolved**: CI confirmed; operadores must still usar el código canónico acordado (trim, sin espacios) |
| Typos in aisle code before DB row | **Open**: slug differs from typo; no auto-link until code matches |
| Path rename on aisle code change | **Open**: new slug; RTMP URL must rotate |