# Supplier recognition — forensic root cause audit

**Job:** `a7db1968-81f1-46ae-9b6f-8d5b546281e5`  
**Execution:** `34171886-e0bb-4458-b25b-67d030b83f49`  
**Inventory:** `ec321684-5bd3-4e48-b75d-6caaf0225199`  
**Aisle:** `68a652c5-65f6-487d-a417-4349b8e3e81c`  
**Audit date:** 2026-09-01  
**Mode:** read-only, evidence-driven

---

## 1. Executive summary

**CONFIRMED ROOT CAUSE:** At job creation (`2026-09-01 13:24:29`), aisle `pasillo 6` pointed to ClientSupplier `c314c8c3-b6fd-490c-98dc-7b1ac40dca47` (`pruebas b`). Table `client_supplier_label_profiles` contained **zero rows** for that supplier. `LabelProfileResolver` therefore chose `resolution_source=DEFAULT` and `source=DINAMIC` for both ITEM and POSITION. That snapshot was frozen into job `a7db1968`. The worker correctly consumed the snapshot (no runtime transform).

Asset `ad40b787` decoded QR payload `A04-R-02|04|RIGHT|02` (POSITION, segmented). Because runtime profiles were DINAMIC, CODE_SCAN used the **legacy product consolidator** (`CodeDetectionConsolidator.consolidate`). The parser treated the full pipe string as `internal_code` with `quantity=null`, producing `MISSING_QUANTITY` + warnings `QUANTITY_MISSING`, `LEGACY_NO_LABEL_ID` → `PENDING_MANUAL_REVIEW`.

**First divergence:** Expected explicit SUPPLIER wiring in DB → Actual: **no wiring rows exist**.

**Secondary blocker (not the cause of DINAMIC runtime, but blocks success even after wiring fix):** ACTIVE extraction profiles for this supplier use `deterministic.payload_structure=SIMPLE` (ITEM: prefix `LPNA`, exact_length 10; POSITION: prefix `A04`, exact_length 6). Sample payloads are **SEGMENTED pipe-delimited** (`LPNA000184|SKU773421|24`, `A04-R-02|04|RIGHT|02`). SUPPLIER validation would reject or mis-parse them until profiles are reconfigured.

**Minimal correction:** (1) Re-activate ITEM and POSITION with `effective_source=SUPPLIER` (atomic wiring upsert). (2) Fix profile deterministic config to SEGMENTED + field mappings. (3) Start a **new job** (snapshot is immutable).

---

## 2. Business state

| Entity | Value |
|--------|-------|
| Client | `8a3c9a01-7494-4be0-99be-595ecbf2b9bd` |
| Inventory | `ec321684-5bd3-4e48-b75d-6caaf0225199` (`pruebas`, `in_review`) |
| Aisle | `68a652c5-65f6-487d-a417-4349b8e3e81c` (`pasillo 6`, `client_supplier_id=c314c8c3…`) |
| ClientSupplier | `c314c8c3-b6fd-490c-98dc-7b1ac40dca47` (`pruebas b`, `active`) |
| Aisle overrides | `item_profile_source_override=null`, `position_profile_source_override=null` |

**ID consistency:** `supplier_id` in `supplier_extraction_profiles` = `ClientSupplier.id` = `aisle.client_supplier_id` = `c314c8c3-b6fd-490c-98dc-7b1ac40dca47`. No mismatch.

---

## 3. Effective wiring (DB, now)

| Kind | Row exists? | source |
|------|-------------|--------|
| ITEM | **NO** | N/A (resolver → DINAMIC) |
| POSITION | **NO** | N/A (resolver → DINAMIC) |

Query: `SELECT * FROM client_supplier_label_profiles WHERE client_supplier_id='c314c8c3-b6fd-490c-98dc-7b1ac40dca47'` → **0 rows**.

Unique constraint: `UQ_cslp_supplier_kind (client_supplier_id, label_kind)`.

**LabelProfileResolver (live, same IDs):**
- ITEM: `source=DINAMIC`, `resolution_source=DEFAULT`
- POSITION: `source=DINAMIC`, `resolution_source=DEFAULT`

---

## 4. Active extraction profiles

| Kind | ACTIVE id | version | activated_at |
|------|-----------|---------|--------------|
| ITEM | `c471485b-6983-4fae-a545-7668202e3e6b` | 8 | `2026-09-01 00:23:55.637913` |
| POSITION | `a1679c90-6ba4-4871-860f-8b586a54c9ce` | 2 | `2026-08-31 19:54:10.491114` |

Profiles are ACTIVE but **decoupled** from runtime source until `client_supplier_label_profiles` rows exist with `source=SUPPLIER`.

---

## 5. Profile correctness vs sample payloads

| Check | ITEM (`LPNA000184\|SKU773421\|24`) | POSITION (`A04-R-02\|04\|RIGHT\|02`) |
|-------|-------------------------------------|----------------------------------------|
| prefix | FAIL (payload is segmented, not 10-char LPNA whole) | FAIL (length 22, not 6) |
| structure | FAIL (ACTIVE=SIMPLE, need SEGMENTED) | FAIL (ACTIVE=SIMPLE, need SEGMENTED) |
| delimiter | FAIL (null vs `\|`) | FAIL |
| segments | FAIL | FAIL |
| mappings | FAIL (WHOLE→label_id only) | FAIL (WHOLE→position_id only) |

**If wiring were SUPPLIER today:** POSITION payload would still fail SIMPLE rules; ITEM sample would fail similarly.

---

## 6. Job snapshot (frozen)

From `engine_params_json.identification_execution.label_profiles`:

```json
"item": {
  "source": "DINAMIC",
  "resolution_source": "DEFAULT",
  "extraction_profile_id": null,
  "extraction_profile_version": null
},
"position": {
  "source": "DINAMIC",
  "resolution_source": "DEFAULT",
  "extraction_profile_id": null,
  "extraction_profile_version": null
}
```

`feature_flag_state.supplier_wiring_warnings`:
- `ACTIVE ITEM extraction profile exists but label_profiles.item.source=DINAMIC (no explicit client_supplier_label_profiles row)`
- `ACTIVE POSITION extraction profile exists but label_profiles.position.source=DINAMIC (no explicit client_supplier_label_profiles row)`

**Snapshot vs DB at job creation:** Both DINAMIC — **consistent, not a snapshot bug**.

Legacy blob `supplier_extraction_profile` embeds ITEM ACTIVE v8 config (OCR-oriented MINIMAL), but CODE_SCAN runtime authority is `label_profiles.*.source`, not that blob alone.

---

## 7. Runtime context

`build_label_validation_context_from_job` reads snapshot only:
- `item_source=DINAMIC`, `position_source=DINAMIC`
- `item_extraction_configuration=null`, `position_extraction_configuration=null` (no embedded SUPPLIER config)
- `StructuredPayloadExtractor` **not invoked** for supplier validation on this path

Processing events (asset `ad40b787`):
- `code_scan.payload_decoded` ✓
- `code_scan.profile_resolved` → ITEM/POSITION `source=DINAMIC`, `profile_version=null`
- `code_scan.asset_finalized` → `MISSING_QUANTITY`, `PENDING_MANUAL_REVIEW`

---

## 8. Asset decode evidence

**Asset 1** `ad40b787-081e-4551-a733-db3d5c06e004`  
File: `ChatGPT Image 31 ago 2026, 09_18_04 p.m..png`

Re-decode (pyzbar, GCS bytes, read-only):
- symbology: `qr`
- payload: **`A04-R-02|04|RIGHT|02`**
- Kind: **POSITION** (segmented location code)

**Asset 2** `f02bf599-71ec-4658-b477-77751bc57678`  
`NO_CODE_SYMBOL_FOUND` → `UNRECOGNIZED` (decoder issue separate from wiring)

---

## 9. Validation trace (asset 1)

1. Decode OK → one QR candidate.
2. Snapshot profiles DINAMIC → unified supplier classifier not eligible for SUPPLIER extraction configs.
3. Branch: legacy `CodeDetectionConsolidator.consolidate(detections)`.
4. `EncodedLabelPayloadParser`: `internal_code=A04-R-02|04|RIGHT|02`, `quantity=null`.
5. Consolidator: `status=MISSING_QUANTITY`, warnings `QUANTITY_MISSING`, `LEGACY_NO_LABEL_ID`.
6. `code_scan_processing_strategy` line ~1115–1126: manual review with `error_code=MISSING_QUANTITY`.

`processing_attempts.validation_result_json`:
```json
{"errors": [], "warnings": ["QUANTITY_MISSING", "LEGACY_NO_LABEL_ID"]}
```

---

## 10. Persistence

| Table | Result |
|-------|--------|
| `job_asset_processing_states` | 1× `PENDING_MANUAL_REVIEW` / `MISSING_QUANTITY`, 1× `UNRECOGNIZED` / `NO_CODE_SYMBOL_FOUND` |
| `product_records` (aisle join) | **0** |
| `positions` (aisle) | **0** |

**Why UI shows 0:** No materialized products/positions/detections — job result counters: `resolved=0`, `manual_review=1`, `unrecognized=1`.

---

## 11. First divergence

| Expected | Actual |
|----------|--------|
| Wiring row ITEM source=SUPPLIER | **No row** → DINAMIC |
| Wiring row POSITION source=SUPPLIER | **No row** → DINAMIC |
| Snapshot SUPPLIER | DINAMIC |
| Runtime SUPPLIER validation | Legacy consolidator |

**First incorrect state:** Missing `client_supplier_label_profiles` rows after profile activation.

---

## 12. Root cause tree

```
Observed: MISSING_QUANTITY + PENDING_MANUAL_REVIEW
  because: CodeDetectionConsolidator returned MISSING_QUANTITY (quantity=null)
    because: EncodedLabelPayloadParser parsed POSITION pipe payload as product code without quantity
      because: CODE_SCAN used legacy DINAMIC consolidator path
        because: label_profiles.item/position.source=DINAMIC in job snapshot
          because: LabelProfileResolver resolution_source=DEFAULT (no stored wiring row)
            because: client_supplier_label_profiles has 0 rows for c314c8c3…
              because: Profile activations (v8 ITEM, v2 POSITION) ran without effective_source=SUPPLIER
                ROOT: Wiring is only persisted on activate when effective_source is explicitly sent;
                      historical “Crear y activar” flows activated extraction profiles but never upserted wiring.
```

---

## 13. Contributing factors

- **Profile schema mismatch:** ACTIVE profiles SIMPLE vs real SEGMENTED QR payloads (blocks success post-wiring).
- **Dual authority UX:** UI draft defaults `source=SUPPLIER` but DB `wiredSource` reads DINAMIC when no row → operator sees “SUPPLIER” intent without persisted wiring.
- **Legacy consolidator on POSITION payloads:** DINAMIC path treats location QR as product code missing quantity.
- **Immutable snapshot:** Job `a7db1968` cannot pick up fixes without new job.
- **Worker build metadata:** No git SHA on job row; wiring warnings prove hardened `start_aisle_processing` code ran at least at job start.

---

## 14. Rejected hypotheses

| Hypothesis | Status |
|------------|--------|
| Scanner/GCS/decoder failure (asset 1) | REJECTED — decode OK |
| Wrong supplier on aisle | REJECTED |
| Aisle DINAMIC override | REJECTED — overrides null |
| Resolver bug | REJECTED — correct DEFAULT when no row |
| Runtime transforms SUPPLIER→DINAMIC | REJECTED — consistent DINAMIC end-to-end |
| Snapshot stale vs DB | REJECTED — both DINAMIC at creation |
| Payload wrong | REJECTED — confirmed POSITION segmented payload |

---

## 15. Hypothesis classification (H1–H20)

| ID | Status | Evidence |
|----|--------|----------|
| H1 | **CONFIRMED** | 0 wiring rows |
| H2 | **LIKELY** | UI draft SUPPLIER vs DB DINAMIC |
| H3 | **CONFIRMED** | ACTIVE profiles + DINAMIC source |
| H4 | **CONFIRMED** | Activate without `effective_source` skips wiring |
| H5 | REJECTED | Same supplier on aisle |
| H6 | REJECTED | Snapshot matches DB |
| H7 | REJECTED | Job after activation; wiring never existed |
| H8 | REJECTED | No aisle override |
| H9 | REJECTED | Resolver behaves per design |
| H10 | **CONFIRMED** | No rows → not found |
| H11 | REJECTED | IDs consistent |
| H12 | REJECTED | No transform |
| H13 | **CONFIRMED** | Snapshot DINAMIC pre-worker |
| H14 | REJECTED | Single supplier |
| H15 | **LIKELY** | Wiring warnings = recent deploy at job start |
| H16 | **CONFIRMED** | Activation without wiring |
| H17 | REJECTED | No row to revert |
| H18 | **CONFIRMED** | SIMPLE vs SEGMENTED payloads |
| H19 | **CONFIRMED** | Legacy consolidator |
| H20 | REJECTED | Payload correct |

---

## 16. Comparative jobs

| Job | created_at | item/pos source | Same supplier? |
|-----|------------|-----------------|----------------|
| `601f3792…` | 2026-09-01 00:25:29 | DINAMIC/DINAMIC | Different aisle; same wiring gap pattern |
| `1c4a2e1c…` | 2026-09-01 00:20:26 | DINAMIC/DINAMIC | Same pattern |
| `a7db1968…` | 2026-09-01 13:24:29 | DINAMIC/DINAMIC | Target job; wiring warnings present |

No job in comparison set had SUPPLIER snapshot — systemic missing wiring, not regression in this job alone.

---

## 17. UI → API → DB flow (wiring)

| Operation | Profile version | Activation | Wiring source |
|-----------|-----------------|------------|---------------|
| Save draft (`activate=false`) | Creates DRAFT | No | **Unchanged** |
| Create + activate (`activate=true`) | Creates + ACTIVE | Yes | **Only if `effective_source` sent** |
| Source dropdown alone | N/A | No | **Not persisted until activate with `effective_source`** |

Frontend (`LabelRecognitionProfileModule.tsx`): activate sends single mutation with `effective_source: draft.source`. Draft save does not.

Backend: `manage_supplier_extraction_profiles.py` → `activate_profile_with_effective_source()` → `upsert_effective_label_source()`.

**What happened for `pruebas b`:** ITEM v8 and POSITION v2 activated **without** wiring upsert (no `effective_source` at activation time / pre-hardening activations).

---

## 18. Timeline

| Time (UTC-3 approx) | Event |
|---------------------|-------|
| 2026-08-31 19:54:10 | POSITION profile v2 ACTIVE |
| 2026-09-01 00:23:55 | ITEM profile v8 ACTIVE |
| 2026-09-01 13:23:43 | Aisle `pasillo 6` created |
| 2026-09-01 13:24:29 | Job `a7db1968` created (snapshot DINAMIC) |
| 2026-09-01 13:24:34–38 | Job executed |

Profiles predated aisle/job; wiring never written.

---

## 19. Minimal fix plan (NOT IMPLEMENTED)

1. **Data/config:** For supplier `c314c8c3…`, re-activate ITEM and POSITION with `effective_source=SUPPLIER` (atomic).
2. **Profile config:** Change deterministic to SEGMENTED with delimiter `|`, correct segment counts and field mappings for ITEM and POSITION samples.
3. **New job:** Required — snapshot immutable.
4. **No migration** needed — table exists; rows missing.
5. **Regression tests:** Already partially covered in `test_supplier_profile_runtime_wiring.py`; add E2E with segmented payloads.
6. **Manual verify:** `LabelProfileResolver` → SUPPLIER; new job events show `source=SUPPLIER`; asset `ad40b787` resolves as POSITION not MISSING_QUANTITY.
7. **Rollback:** Set wiring rows to DINAMIC or delete rows (reverts to DEFAULT).

---

## 20. Mandatory Q&A (25)

1. **Supplier on aisle?** `c314c8c3-b6fd-490c-98dc-7b1ac40dca47` (`pruebas b`)
2. **Same as UI-edited supplier?** Yes (only supplier on aisle; extraction profiles under same id)
3. **ITEM wiring exists?** No
4. **ITEM source?** DINAMIC (DEFAULT)
5. **POSITION wiring exists?** No
6. **POSITION source?** DINAMIC (DEFAULT)
7. **ITEM ACTIVE?** v8 `c471485b…`
8. **POSITION ACTIVE?** v2 `a1679c90…`
9. **Profiles valid for payloads?** **No** (SIMPLE vs SEGMENTED)
10. **Resolver at job creation?** DINAMIC/DEFAULT
11. **Why?** No `client_supplier_label_profiles` rows
12. **Snapshot label_profiles?** DINAMIC both kinds, null profile versions
13. **job_validation_context?** DINAMIC, no extraction configs embedded
14. **Worker transform?** No — consumed snapshot
15. **pyzbar payload?** `A04-R-02|04|RIGHT|02`
16. **Kind?** POSITION
17. **StructuredPayloadExtractor?** No (SUPPLIER path not active)
18. **Validations run?** Legacy consolidator only
19. **MISSING_QUANTITY emitter?** `CodeDetectionConsolidator` → `code_scan_processing_strategy`
20. **Why legacy?** DINAMIC snapshot → consolidator branch
21. **Persisted state?** Manual review + unrecognized; 0 products/positions
22. **UI zero?** No materialized records
23. **Worker latest code?** LIKELY yes (wiring warnings); SHA UNVERIFIED
24. **First divergence?** Missing wiring rows
25. **Root cause set?** (1) Missing wiring persistence on activate; (2) profile config incompatible with payloads (secondary)

---

**Final recommendation:** `READY_TO_IMPLEMENT` — root cause proven; fix is targeted (wiring backfill via re-activate + profile config + new job).
