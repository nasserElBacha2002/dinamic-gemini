# Mobile CODE_SCAN Phase 3 — Implementation Report

## Status

`IMPLEMENTED_WITH_LIMITATIONS`

## Architecture

Shadow-mode local barcode/QR detection after image prepare, before/alongside upload:

```
CAPTURED → PREPARED → local CODE_SCAN (draft) → UPLOAD → /process (server authority)
```

Local result is diagnostic only. Server pipeline (`POST /assets`, `POST /process`, CODE_SCAN / INTERNAL_OCR / fallback, final persistence) is unchanged.

Layers:

| Concern | Module |
| --- | --- |
| Detection | `LocalBarcodeDetector` (ML Kit) via Expo module |
| Parsing | `labelPayload.ts` (pure TS, server-aligned) |
| Consolidation | `codeDetectionConsolidator.ts` (one image ≤ one label) |
| Strategy | `LocalCodeScanStrategy` (timeout, flags, capability) |
| Persistence | `local_detection_drafts` (migration v8) |
| Compare | `compareLocalVsServer` + JobMonitor hook |
| UI | operational status only on Uploads screen |

## SDK chosen

**Google ML Kit Barcode Scanning** (`com.google.mlkit:barcode-scanning:17.3.0`)

Rationale:

- Offline / on-device (no per-scan network download of models in normal use)
- Compatible with Expo prebuild via existing `capture-foreground-service` native module
- Maintained Google library; Apache-style redistribution via Maven
- Enough formats for inventory labels without enabling all symbologies

Enabled formats only:

`QR_CODE`, `CODE_128`, `CODE_39`, `EAN_13`, `EAN_8`, `UPC_A`, `UPC_E`

## Contracts

Neutral fixtures: `contracts/code-scan/v1/`

- `valid.json`, `invalid.json`, `ambiguous.json`, `constants.json`, `schema.json`
- Executed by mobile Jest + Python `test_code_scan_shared_contracts.py`

Parser version: `1.0.0`  
Detector version: `mlkit-barcode-1.0.0`

## States

Draft statuses: `NOT_APPLICABLE | PENDING | SCANNING | RESOLVED | UNRESOLVED | INVALID | AMBIGUOUS | FAILED`

Quantity: only when explicit in payload; otherwise `quantity=null` + `MISSING|INVALID`.

Ambiguity: multiple distinct valid codes → `AMBIGUOUS` (no arbitrary first pick).

## Persistence

Table `local_detection_drafts` with unique key:

`(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint)`

Stores hash + short sanitized preview; not full sensitive payload in logs.

## Feature flags (default **false**)

- `mobileLocalCodeScan` ← `DINAMIC_FLAG_LOCAL_CODE_SCAN`
- `mobileLocalCodeScanShadowCompare` ← `DINAMIC_FLAG_LOCAL_CODE_SCAN_COMPARE`
- `mobileLocalCodeScanDebugMetrics` ← `DINAMIC_FLAG_LOCAL_CODE_SCAN_DEBUG`

Kill switch: flags off → no scan, no drafts from strategy path, upload unchanged.

## Observability events

`local_scan_started|completed|failed|timeout|ambiguous|result_compared`

No internal codes, quantities, or raw payloads in logs.

## Security

- Parametrized SQL
- Payload length capped (preview 32, rawValue to detector 512)
- Local input treated as untrusted
- No backend secrets in scanner path

## Files modified / created (Phase 3 core)

- `contracts/code-scan/v1/*`
- `mobile/src/core/labelPayload.ts`, `codeDetectionConsolidator.ts`, `payloadFingerprint.ts`, `featureFlags.ts`
- `mobile/src/features/localCodeScan/*`
- `mobile/src/database/migrations/migrations.ts` (v8)
- `mobile/src/database/repositories/localDetectionDraftRepository.ts`
- `mobile/src/features/upload/uploadQueue.ts` (post-prepare hook)
- `mobile/src/features/processing/jobMonitor.ts` (shadow compare)
- `mobile/src/runtime/bootstrap/createAppServices.ts`
- `mobile/src/screens/UploadsScreen.tsx`
- `mobile/modules/capture-foreground-service/.../LocalBarcodeDetector.kt` + module bridge + ML Kit dep
- Tests: mobile + `backend/tests/.../test_code_scan_shared_contracts.py`

## Limitations

See final status section in the implementation report response / metrics report.

### [HIGH] Samsung S10+ release matrix not measured

Evidencia: no device dataset run in this session.  
Impacto: cannot claim resolved/false-positive rates.  
Motivo: requires physical release build + labeled corpus.  
Próximo paso: run manual matrix (§31) with flags on.

### [MEDIUM] Shadow compare currently `NOT_COMPARABLE`

Evidencia: aisle status API used by JobMonitor has no reliable `client_file_id` → code/qty mapping.  
Impacto: compare metrics not populated.  
Motivo: avoid inventing array-order matching (spec).  
Próximo paso: wire mapped positions/evidence API when approved.

### [LOW] Local scan runs on JS prepare path only

Evidencia: hook in `UploadQueue.preparePhoto`. Native WorkManager uploads already-prepared files.  
Impacto: OK if prepare remains JS-owned.  
Próximo paso: if native prepare is added later, invoke the same strategy there.

### [LOW] `.gitignore` previously ignored contract JSON

Evidencia: global `*.json` rule hid `contracts/code-scan/v1/*`.  
Impacto: fixtures would not version until exception added.  
Motivo: fixed with `!contracts/code-scan/**/*.json`.  
Próximo paso: ensure CI includes these paths.
