# Mobile Upload Phase 1 — Implementation Report

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`

## Architecture

```text
ImagePreparationPolicy.resolve(mode, network, flags, limits)
        → ImagePreparationProfile
        → preparePhotoForUpload (single manipulate when possible)

UploadConcurrencyPolicy.resolve(network, serverConcurrency, flag)
        → effective concurrency (cap 4)

UploadQueue.tick
        → prepare with backpressure (MAX_PREPARED_PENDING)
        → uploadPreparedBatch with AbortController (flag)
        → Phase 0 observability events (+ profile / concurrency attrs)
```

Server `/assets` and `/process` unchanged. No local CODE_SCAN/OCR.

## Policies

### Preparation (`DefaultImagePreparationPolicy`)

| Mode | profileId | maxEdge (when cap on) | jpegQuality (adaptive) |
| ---- | --------- | --------------------: | ---------------------: |
| CODE_SCAN | code_scan_v1 | 3000 (`DEFAULT_MAX_DIMENSION_PX`) | 0.90 (cellular −0.03) |
| INTERNAL_OCR | internal_ocr_v1 | 3000 | 0.92 |
| LEGACY_LLM | legacy_llm_v1 | ≤2560 | 0.88 |
| UNKNOWN | unknown_safe_v1 | 3000 | 0.90 |

**Decisión:** Mode hint is optional on `UploadQueueOptions.processingModeHint`. Capture/upload usually runs **before** `/process` mode selection → default **UNKNOWN** safe profile.  
**Evidencia:** Mode is chosen in process UI (`processingMode.ts`), not at capture enqueue.  
**Implementación:** `normalizePreparationProcessingMode` + optional hint.  
**Riesgo:** CODE_SCAN vs OCR profile may not apply at prepare time.  
**Mitigación:** UNKNOWN is OCR-leaning quality; mode-specific profiles remain testable for later preference wiring.  
**Validación:** Unit tests for all modes.

### Concurrency (`DefaultUploadConcurrencyPolicy`)

| Network | Adaptive on | Adaptive off |
| ------- | -----------: | -----------: |
| wifi/ethernet | min(3, server, 4) | min(2, server, 4) |
| cellular | min(2, server, 4) | min(2, server, 4) |
| unknown | min(2, server, 4) | min(2, server, 4) |
| offline | 0 | 0 |

## HEIC flag

**Decisión:** Keep `heicConvertToJpeg` and **wire it**.  
**Evidencia:** Backend accepts HEIC (`pillow-heif` worker normalize); mobile allowlist includes HEIC. Flag previously ignored.  
**Implementación:** `profile.convertHeic` from flag; when false → `heic_passthrough` without convert.  
**Riesgo:** Some devices/paths may struggle uploading raw HEIC.  
**Mitigación:** Default remains convert=true.  
**Validación:** Policy + prepare path; flag unit tests.

## Feature flags (independent kill switches)

| Flag | Env | Default |
| ---- | --- | ------- |
| uploadDimensionCap | `DINAMIC_FLAG_UPLOAD_DIM_CAP` | on |
| uploadAdaptiveQuality | `DINAMIC_FLAG_UPLOAD_ADAPTIVE_QUALITY` | on |
| uploadAdaptiveConcurrency | `DINAMIC_FLAG_UPLOAD_ADAPTIVE_CONCURRENCY` | on |
| uploadAbortEnabled | `DINAMIC_FLAG_UPLOAD_ABORT` | on |
| heicConvertToJpeg | `DINAMIC_FLAG_HEIC_JPEG` | on |

Flags off → legacy dimension (byte-only resize), legacy qualities 0.92/0.85, concurrency cap 2, cancel without multipart abort.

## Cancellation

- Batch multipart is atomic: aborting one photo aborts the whole batch request.
- Cancelled photo → `excluded` + `UPLOAD_ABORTED`.
- Sibling photos → re-`queued` with `UPLOAD_ABORTED` (not permanent; no forced retry delay storm).
- `apiClient` links caller `AbortSignal` with timeout controller.

## Observability (Phase 0 reuse)

Added attrs: `preparation_profile_id/version`, `dimension_cap_applied`, `format_conversion_applied`, `quality_applied`, `configured_concurrency`, `effective_concurrency`, `active_upload_count`.

## Files changed (high level)

- `mobile/src/core/imagePreparationPolicy.ts` (new)
- `mobile/src/core/uploadConcurrencyPolicy.ts` (new)
- `mobile/src/features/upload/photoPrepare.ts`
- `mobile/src/features/upload/uploadQueue.ts`
- `mobile/src/services/api/apiClient.ts` (abort+timeout link)
- `mobile/src/core/featureFlags.ts`, `app.config.ts`, `.env.example`, README
- tests + audit docs

## Limitations

### [HIGH] Samsung S10+ release comparison not executed in this session

**Evidencia:** No release device baseline numbers filled.  
**Impacto:** Acceptance item 18–19 incomplete for measured uplift.  
**Motivo:** Agent environment; Metro/dev available but not full release matrix.  
**Próximo paso:** Run scenarios; fill `mobile-upload-phase1-baseline-comparison.md`.

### [MEDIUM] Processing-mode profile often UNKNOWN at prepare time

**Evidencia:** Mode selected at process start.  
**Impacto:** CODE_SCAN vs OCR quality differentiation limited until hint/preference is set earlier.  
**Motivo:** Architecture of current UX.  
**Próximo paso:** Persist aisle/user preferred mode onto session before upload.

### [LOW] Second manipulate pass still possible if over byte budget after cap

**Evidencia:** `photoPrepare` second pass for rare oversized outputs.  
**Impacto:** Occasional double JPEG cycle.  
**Motivo:** Must respect server max file size.  
**Próximo paso:** Tune first-pass quality/edge with measured data.
