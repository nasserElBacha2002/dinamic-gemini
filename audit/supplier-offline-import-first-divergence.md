# Supplier offline import — first divergence report

Date: 2026-09-01  
Supplier: `pruebas b` (ClientSupplier segmented ITEM v10 / POSITION v3)

## Call graph (actual code paths)

```
QR/CODE128 scan
  → LocalCodeScanStrategy.execute()
  → runProfileAwareLocalScan() + consolidateCodeDetections()
  → local_detection_drafts (product_results_json, internal_code, position_snapshot_json, recognition_profile_snapshot_json)
  → buildLocalCsvRows() / ZIP export
  → backend parse_local_csv()
  → LocalCsvImportRow → LocalCsvProductiveResult
  → LocalCsvPositionMaterializer.materialize()
  → Position + ProductRecord → operational UI
```

## Stage table — golden payloads

### ITEM `LPNA000184|SKU773421|24`

| Stage | label_kind | label_id | sku/internal_code | quantity | profile | Correct? |
|-------|------------|----------|-------------------|----------|---------|----------|
| Scanner | — | — | — | — | — | ✓ (decode OK) |
| Profile-aware validation (when SUPPLIER profile resolved) | ITEM | LPNA000184 | SKU773421 | 24 | v10 | ✓ |
| Profile-aware validation (when profile **missing**) | — | — | — | — | — | ✗ skipped |
| Legacy `parseEncodedLabelPayload` fallback | PLAIN | — | **full raw string** | MISSING | — | ✗ |
| Draft persist (`internal_code`) | — | — | **LPNA000184\|SKU773421\|24** | null | — | ✗ |
| Export `productsForPhoto` fallback | — | — | **raw as SKU** | empty→0 | — | ✗ |
| Import parse | — | — | **raw as internal_code** | null | — | ✗ |
| Materialize `_quantity_for` | — | — | **raw SKU** | **0** | — | ✗ |
| UI | ITEM | — | **raw in SKU column** | **0** | Requiere revisión | ✗ |

**First broken stage (profile missing path):** `consolidateCodeDetections` / `parseEncodedLabelPayload` — PLAIN grammar treats entire segmented string as `internalCode` when PIPE pattern (2 segments) does not match.

**First broken stage (profile resolved but legacy wins):** `localCodeScanStrategy` persists `consolidated.internalCode` alongside valid `product_results_json` in edge cases; export fallback reads `draft.internal_code` when JSON empty.

### POSITION `A04-R-02|04|RIGHT|02`

| Stage | position_id | pallet | side | level | sku | quantity | Correct? |
|-------|-------------|--------|------|-------|-----|----------|----------|
| Profile-aware validation (resolved) | A04-R-02 | 04 | RIGHT | 02 | — | null | ✓ |
| Legacy fallback | — | — | — | — | **full raw** | MISSING | ✗ |
| Draft | snapshot OK or missing | | | | **raw in internal_code** | — | ✗/△ |
| Export | position fields from snapshot | ✓ if snapshot | | | else **product row** | | ✗ |
| Import | position_payload_raw plain text | | | | **raw SKU** | 0 | ✗ |
| Materialize | `entity_uid=local_csv:{id}` | position_code often empty | | | ProductRecord created | 0 | ✗ |
| UI | **local_csv:uuid** | | | | **raw in SKU** | 0 | ✗ |

**First broken stage (profile missing):** same legacy parser — POSITION segmented payload is not JSON `DINAMIC_POSITION`, so `parseDinamicPositionPayload` returns null; legacy PLAIN path stores full string as product code.

**Import/materialize divergence:** `_validate_position_payload` requires JSON; mobile exports supplier `position_payload_raw` as plain segmented text → validation fails → business `position_code` not applied; synthetic `local_csv:{uuid}` used in summary.

## Root causes (ordered)

1. **Mobile legacy revival** — When supplier profile context is unavailable, `parseEncodedLabelPayload` stores the full segmented string as `internalCode` instead of failing closed.
2. **Mobile export fallback** — `productsForPhoto()` uses `draft.internal_code` when `product_results_json` is empty, exporting raw payload as SKU.
3. **Mobile scan persist** — `persistInternalCode` can copy legacy `consolidated.internalCode` (raw) even when supplier validation succeeded on a parallel path.
4. **Backend quantity sentinel** — `_quantity_for()` maps `null → 0`, producing zero quantity in UI and false review triggers.
5. **Backend position payload contract** — JSON-only validation rejects supplier plain-text `position_payload_raw`; exported `position_code` / hierarchy columns not promoted to business position when validation fails.
6. **Backend materializer** — All non-`LOCAL_POSITION_LABEL` rows become `ProductRecord`; POSITION-only rows exported incorrectly as `LOCAL_CODE_SCAN` with raw SKU.

## Correction strategy

- **Option A (preferred):** Mobile exports semantic fields (`label_id`, `sku`, `quantity`, position hierarchy) from `product_results_json` / `recognition_profile_snapshot_json`; never raw segmented string as `internal_code`. Backend revalidates when notes carry profile snapshot metadata.
- **Backend safety net:** Accept plain-text supplier position evidence when CSV position columns populated; fix quantity null handling; use `position_label_id`/`position_code` for display instead of `local_csv:{uuid}`.

## Out of scope

- Scanner / GCS / CODE_SCAN timeout changes
- Modifying `pruebas b` supplier profiles
- `.dinamic` package format (CSV/ZIP path only)
