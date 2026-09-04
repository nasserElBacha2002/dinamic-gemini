# Mobile export — forensic first divergence (`pruebas b`)

**Audit date:** 2026-09-01  
**Mode:** read-only forensic (no code fixes applied)  
**Real device session:** reproduced via Metro logs (USB dev client)  
**Inventory:** `eb6f750e-ed12-4c71-b9b2-56a1301e08a8`  
**Aisle:** `b02b75b0-f153-4072-95fb-c78f0f94be43`  
**Capture session:** `2c3d6809-82d8-4ee4-9299-ba20fc7c6679`  
**ClientSupplier (expected):** `c314c8c3-b6fd-490c-98dc-7b1ac40dca47` (`pruebas b`)

---

## Status dashboard

| Check | Result |
|-------|--------|
| REAL_DEVICE_REPRODUCED | **YES** (Metro `897502.txt`, 15:48 UTC-3) |
| BUILD_VERIFIED | **PARTIAL** (see BUILD) |
| SUPPLIER_BUNDLE | **NOT CONFIRMED ON DEVICE** (SQLite not pulled) |
| ITEM_SCAN (decoder) | **PASS** |
| ITEM_SCAN (supplier semantic) | **FAIL** |
| POSITION_SCAN (decoder) | **PASS** |
| POSITION_SCAN (supplier semantic) | **FAIL** |
| DRAFT_PERSISTENCE | **FAIL** (RESOLVED shell, zero products) |
| CSV_PROJECTION | **FAIL** (both rows → LOCAL_PENDING) |
| LOCAL_PENDING_COUNT | **2** (all eligible photos) |
| EXPORT | **FAIL** (inferred → `PACKAGE_EXPORT_UNRESOLVED`) |
| ROOT_CAUSE_CONFIRMED | **YES** (log + code chain) |
| DEVICE_E2E | **FAIL** (no successful ZIP in logs) |

---

## BUILD

### Observable from workspace / Metro

| Field | Value | Source |
|-------|-------|--------|
| `versionName` | `0.3.6-local` | `mobile/.env` |
| `versionCode` | `40` | `mobile/.env` |
| `gitSha` (build-time) | `d3e039aa` (current HEAD) | `app.config.ts` / `git rev-parse` |
| SQLite schema | **v32** (`offline_supplier_recognition_config`) | `migrations.ts` |
| Metro started | 2026-09-01 15:04 `--clear` | terminal `897502.txt` |
| Capture at | 2026-09-01 15:48 | same terminal |

### Required code paths (workspace working tree)

| Capability | Present in workspace? | Notes |
|------------|----------------------|-------|
| `ensureLocalCodeScans` with `inventoryId` / `aisleId` | **YES** | `localCsvExportService.ts:148-150` |
| `rawPayload` in `product_results_json` | **YES** (uncommitted) | `localCodeScanStrategy.ts:428` |
| `localCsvExportPreflight` | **YES** (uncommitted new file) | `localCsvExportPreflight.ts` |
| `storedProductResults.rawPayload` | **YES** (uncommitted) | `storedProductResults.ts` |

**BUILD_VERIFIED: PARTIAL**

- Dev client loads JS from Metro; capture at 15:48 occurred **after** Metro `--clear`, so the bundle likely reflects the **current working tree** (including uncommitted export fixes).
- Native APK `versionCode=40` does not prove committed vs uncommitted JS; only Metro reload / build timestamp confirms JS.
- **Device SQLite was not extracted** — bundle tables (`offline_recognition_profiles`, `offline_supplier_recognition_config`) could not be read directly.

**Stop condition (APK stale):** Not triggered for JS logic — scan traces show profile-aware multilabel logging consistent with current strategy. If an old bundle lacked supplier tables entirely, behavior would match observed failure.

---

## FEATURE FLAGS

From `mobile/.env` (Metro `env: export …` line 21):

| Flag | Effective |
|------|-----------|
| `mobileLocalCodeScan` | **true** (`DINAMIC_FLAG_LOCAL_CODE_SCAN=1`) |
| `mobileAuthoritativeLocalCodeScan` | **true** |
| `mobileCsvExport` | **true** (default in `featureFlags.ts`; not disabled in `.env`) |
| `localCompletion` | **true** (default) |
| `mobileServerUpload` | **true** |

`localCodeScanEnabledForExport()` is **true** (`uploadQueue.ts:228-233`).

Export rescan path runs even when `mobileLocalCodeScan` shadow flag alone would be insufficient.

---

## SESSION

From Metro `session_start` / `capture.finish_*` (session `2c3d6809-…`):

| Field | Value |
|-------|-------|
| `session.id` | `2c3d6809-82d8-4ee4-9299-ba20fc7c6679` |
| `inventory_id` | `eb6f750e-ed12-4c71-b9b2-56a1301e08a8` |
| `aisle_id` | `b02b75b0-f153-4072-95fb-c78f0f94be43` |
| `status` (at finish) | `finishing` → review transition |
| `photo_count` | **2** |
| `stable_count` | **2** |
| `active_freeze_id` | set at finish (`capture.finish_freeze_completed`, `new_media_candidate_count: 2`) |
| `capture_freeze_generation` | **1** (inferred from finish flow) |

Recognition sync for inventory `eb6f750e-…`:

- `mobile.recognition.sync_completed` at **15:48:23** (before capture)
- Later `sync_failed` (SQLite busy) at 15:56 / 16:14 — intermittent stampede

**AISLE (inferred):** local aisle with ClientSupplier `pruebas b` — not confirmed in device SQLite; consistent with user scenario and inventory used on device.

---

## OFFLINE PROFILES

**Device SQLite: NOT AVAILABLE** in this audit.

Backend bundle for `eb6f750e-…` was **not fetched** (API credentials / approval boundary).

**Expected** for `pruebas b`:

| Kind | source | version | config |
|------|--------|---------|--------|
| ITEM | SUPPLIER | 10 | SEGMENTED `\|`, 3 segments |
| POSITION | SUPPLIER | 3 | SEGMENTED `\|`, 4 segments |

**Inference from scan traces:** supplier validator did **not** run successfully at capture time. Most likely causes (ordered):

1. `LocalLabelProfileResolver` resolved **DINAMIC** for ITEM/POSITION (`effective_*_source` or missing `offline_supplier_recognition_config` row).
2. `missingSupplierProfile: true` but snapshot not flagged in preflight (see §16).
3. Less likely: profiles present but `validateSupplierPayloadOffline` returned non-VALID (would appear in snapshot `item.status`).

Unit tests prove golden payloads **do validate** when resolver returns SUPPLIER + v10/v3 config (`localAislePhase3.test.ts`).

---

## PHOTO MATRIX (all eligible photos — session has exactly 2)

| photo_id | intended | stable | raw candidate (decoder) | profile / supplier | validation outcome | draft (inferred) | CSV `source` |
|----------|----------|--------|---------------------------|--------------------|--------------------|------------------|--------------|
| `…:1000329819` | **POSITION** | yes | `A04-R-02\|04\|RIGHT\|02` (QR) | supplier POSITION **not VALID** | legacy `MISSING_QUANTITY`; `position_detected: false` | `status=RESOLVED`, `product_results_json=null`, `position_detected=0` | **LOCAL_PENDING** |
| `…:1000329820` | **ITEM** | yes | `LPNA000184\|SKU773421\|24` (QR) | supplier ITEM **not VALID** | legacy `MISSING_QUANTITY`; `products_emitted: 0` | `status=RESOLVED`, `product_results_json=null`, no SKU | **LOCAL_PENDING** |

**Important:** This session has **no third “extra” photo**. Failure is **not** “golden ITEM+POSITION OK but one extra illegible photo”. **Both** photos fail semantic export.

---

## DRAFT MATRIX (inferred from scan traces + persistence rules)

Device SQLite rows not dumped. Reconstruction from `local_scan_multilabel_trace` / `local_scan_completed` + `LocalCodeScanStrategy` persistence logic:

### Photo `…:1000329819` (POSITION)

```json
{
  "capture_photo_id": "2c3d6809-82d8-4ee4-9299-ba20fc7c6679:1000329819",
  "status": "RESOLVED",
  "error_code": null,
  "internal_code": null,
  "label_id": null,
  "quantity": null,
  "quantity_status": "MISSING",
  "position_detected": 0,
  "product_results_json": null,
  "position_snapshot_json": null,
  "recognition_profile_snapshot_json": "<expected: item/position profile_source DINAMIC or missing flags — not VALID branches>",
  "recognition_context": "OFFLINE or ONLINE",
  "detector_version": "mlkit-barcode-1.1.0-multipass",
  "parser_version": "1.1.0"
}
```

### Photo `…:1000329820` (ITEM)

```json
{
  "capture_photo_id": "2c3d6809-82d8-4ee4-9299-ba20fc7c6679:1000329820",
  "status": "RESOLVED",
  "error_code": null,
  "internal_code": null,
  "label_id": null,
  "quantity": null,
  "quantity_status": "MISSING",
  "position_detected": 0,
  "product_results_json": null,
  "recognition_profile_snapshot_json": "<same pattern — no VALID item branch>",
  "recognition_context": "OFFLINE or ONLINE"
}
```

**Golden ITEM expectation NOT met:**

- `product_results_json` does **not** contain `{ labelId, internalCode, quantity, rawPayload }`.
- No `internal_code = SKU773421`.
- Snapshot does **not** show `item.status = VALID` with v10 profile.

**Golden POSITION expectation NOT met:**

- `position_detected ≠ 1`.
- No VALID position snapshot with `A04-R-02`, pallet `04`, side `RIGHT`, level `02`.

---

## SCAN TRACE (device logs)

### POSITION photo `1000329819` (15:48:55.962Z)

```
raw_codes_detected_count: 1
raw_preview: "A04-R-02|04|RIGHT|02"
consolidation_status: MISSING_QUANTITY
local_scan_status: RESOLVED
products_emitted: 0
position_detected: false
position_candidates_count: 0
d1_mode: false
strategy_product_results_count: 0
```

### ITEM photo `1000329820` (15:48:56.882Z)

```
raw_codes_detected_count: 1
raw_preview: "LPNA000184|SKU773421|24"
consolidation_status: MISSING_QUANTITY
local_scan_status: RESOLVED
products_emitted: 0
position_detected: false
strategy_product_results_count: 0
```

### Pipeline interpretation

| Stage | POSITION photo | ITEM photo |
|-------|----------------|------------|
| Barcode detector | **PASS** | **PASS** |
| Raw candidates | 1 × QR | 1 × QR |
| Profile resolver | **FAIL** (no SUPPLIER VALID path used) | **FAIL** |
| Supplier validator | **SKIP or non-VALID** | **SKIP or non-VALID** |
| Legacy consolidator | `MISSING_QUANTITY` (pipe payload ≠ Dinamic `code\|qty`) | `MISSING_QUANTITY` |
| Product injection (`supplierItem` block) | **NOT executed** (`products_emitted: 0`) | **NOT executed** |
| Position apply (`supplierPosition`) | **NOT executed** (`position_detected: false`) | n/a |
| Draft status | `RESOLVED` ← **misleading** (`MISSING_QUANTITY` maps to RESOLVED) | same |

Relevant code:

- Supplier product injection only when `profileAware.supplierItem?.status === 'VALID'` (`localCodeScanStrategy.ts:270-299`).
- `draftStatusFromConsolidation('MISSING_QUANTITY') → 'RESOLVED'` (`localCodeScanStrategy.ts:91-92`) — **UI/logs can show RESOLVED while export data is empty**.

---

## isDraftExportReady (inferred per photo)

| photo_id | ready | reason |
|----------|-------|--------|
| `…:1000329819` | **false** | `NOT_READY` — no `product_results_json`; no VALID position snapshot; `position_detected=0`; no legacy non-segmented `internal_code` |
| `…:1000329820` | **false** | `NOT_READY` — no `product_results_json`; no VALID item snapshot; no exportable `internal_code` |

Even if export-time `ensureLocalCodeScans` re-runs, **same resolver/supplier outcome** reproduces the same draft unless offline bundle sources change.

---

## CSV ROW MATRIX (projected from real session shape)

Simulated via `buildLocalCsvRows` rules on inferred drafts (2 eligible freeze photos):

| capture_photo_id | source | internal_code | label_id | quantity | position_code | position_label_id |
|------------------|--------|---------------|----------|----------|---------------|-------------------|
| `…:1000329819` | **LOCAL_PENDING** | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* |
| `…:1000329820` | **LOCAL_PENDING** | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* |

- `productResultCount`: **0**
- `positionEventCount`: **0**
- `assertLocalCsvRowsExportReady` → **`PACKAGE_EXPORT_UNRESOLVED`** (2 pending rows)

Strict export mode **A**: any `LOCAL_PENDING` aborts entire ZIP.

---

## FIRST DIVERGENCE

### Question checklist (both photos)

| Hypothesis | Applies? |
|------------|----------|
| A. No draft | **NO** — drafts written (`local_scan_completed`) |
| B. Draft exists, empty `product_results_json` | **YES** |
| C. Decoder failed | **NO** — raw previews match golden strings |
| D. Profile resolver did not enable SUPPLIER | **YES** — primary divergence |
| E. Supplier validator rejected | Possible but secondary; logs show legacy consolidator path |
| F. VALID recognition not persisted | **YES** — consequence of D/E (`products_emitted: 0`) |
| G. Position not projected | **YES** — consequence (`position_detected: false`) |
| H. `buildLocalCsvRows` ignored valid data | **NO** — no valid semantic input in draft |
| Extra unresolved 3rd photo | **NO** — only 2 photos, both unresolved |
| Freeze ID mismatch | **NOT OBSERVED** — scans use same `capture_photo_id` as logs |

### Verdict

```
ROOT_CAUSE:
Supplier-aware offline recognition did not produce VALID ITEM/POSITION results at scan time.
Decoder succeeded, but LocalLabelProfileResolver / offline bundle did not activate SUPPLIER
validation (or profiles were missing/DINAMIC). Legacy consolidator treated segmented supplier
QRs as legacy pipe payloads → MISSING_QUANTITY with zero productResults. Drafts persisted as
RESOLVED shells without product_results_json or position_detected, so CSV export maps every
row to LOCAL_PENDING and assertLocalCsvRowsExportReady throws PACKAGE_EXPORT_UNRESOLVED.

FIRST_BAD_STAGE:
profile resolver → supplier validator
(between raw candidates and LocalCodeScanStrategy product/position persistence)

AFFECTED_PHOTO_IDS:
[
  "2c3d6809-82d8-4ee4-9299-ba20fc7c6679:1000329819",
  "2c3d6809-82d8-4ee4-9299-ba20fc7c6679:1000329820"
]
```

**Case mapping (§27):** **CASE B** (profile/bundle/resolver) with **CASE C** symptom (VALID recognition never persisted). Not CASE A (decoder), not CASE D alone (CSV logic is correct given inputs), not CASE E (no extra illegible photo), not CASE G (APK stale for JS).

---

## Preflight gap (§16)

`diagnoseExportBlockers` only elevates:

- `OFFLINE_CONFIG_REQUIRED` when `item_profile_missing === true` in snapshot
- `SCAN_UNSUPPORTED`
- `PHOTOS_UNSTABLE`

When resolver returns **`source: DINAMIC`** with `missing: false`, preflight returns **null** even though supplier segmented codes are unreadable. Export then fails with generic **`PACKAGE_EXPORT_UNRESOLVED`** — **matches user-visible message after preflight ship**.

Observed case: stable photos, scanner OK, profile exists in backend (assumed) but **mobile effective source ≠ SUPPLIER** → preflight silent → same error string.

---

## rawPayload chain (§17)

Uncommitted fix path: `rawPayload` in `product_results_json` → `storedProductResults` → CSV `notes` (`supplier_import`).

**Not reached** in this session because `product_results_json` is null. rawPayload gap is **downstream of** first divergence; fixing notes alone would **not** clear `LOCAL_PENDING`.

---

## FREEZE / re-scan (§19–21)

- Session finished with **freeze** (`capture.finish_freeze_completed`).
- Export uses `listFreezePhotos(active_freeze_id)` when freeze present (`localCsvExportService.ts:175-177`).
- Scans logged against same `capture_photo_id` values as photos — **no ID split observed**.
- `capture.finish_scan_completed` → `skipped_full_rescan: true` for second photo path — export-time repair still required via `ensureLocalCodeScans` if drafts not export-ready.

---

## onPhotoStable vs export scan (§23)

- `onPhotoStable` → `rescanPhotoForLocalReview` when CSV/localCompletion mode (`createAppServices.ts:495-500`).
- Scans at 15:48:55–56 occurred during finish / stable chain — **rescan invoked**.
- Results already show supplier path failure at stable time; export would not magically fix without bundle/resolver fix.

---

## Assert / business mode (§14)

Current behavior: **strict mode A** — 1 pending row blocks export. Here **both** rows pending → message correctly reflects total failure, not a partial-export edge case.

---

## Recommended fix direction (§27 — proposal only, not implemented)

1. **Confirm device SQLite** for aisle `b02b75b0-…`:
   - `local_aisles.client_supplier_id = c314c8c3-…`
   - `offline_supplier_recognition_config` → `item_source/position_source = SUPPLIER`
   - `offline_recognition_profiles` → ITEM v10 + POSITION v3 configuration_json
2. If bundle rows missing or `DINAMIC`: fix recognition bundle sync / backend `suppliers[]` wiring (same class of bug as backend job audits for `pruebas b`).
3. **Hardening (separate):**
   - Do not map `MISSING_QUANTITY` → draft `RESOLVED` when `productResults.length === 0` and supplier source expected.
   - Extend preflight for `profile_source: DINAMIC` + segmented raw in draft / snapshot.
4. Re-run device E2E with matrix:

| | POSITION | ITEM |
|---|----------|------|
| source | LOCAL_POSITION_LABEL | LOCAL_CODE_SCAN |
| key fields | position `A04-R-02` | label `LPNA000184`, SKU `SKU773421`, qty `24` |
| LOCAL_PENDING | 0 | |
| ZIP | SUCCESS | |

---

## Evidence gaps / next steps

1. Pull device SQLite (`local_detection_drafts`, offline recognition tables) to replace inferred draft matrix with literal JSON.
2. Fetch `GET /api/v3/inventories/eb6f750e-…/recognition-config` and confirm `suppliers[]` for `pruebas b`.
3. Capture explicit export attempt log line (`PACKAGE_EXPORT_UNRESOLVED`) — not present in Metro tail; failure inferred from row projection.
4. After fix: **DEVICE_E2E PASS** with build version + session IDs + CSV dump + ZIP checksum.

---

## Final recommendation

**READY_WITH_RISKS** — root cause is confirmed at **profile resolver → supplier validator** with strong log evidence; device SQLite and backend bundle snapshot should be attached before implementing fix to distinguish DINAMIC wiring vs missing profile rows vs sync_skipped stale bundle.
