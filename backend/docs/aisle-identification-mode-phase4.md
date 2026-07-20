# Aisle identification — Phase 4 (INTERNAL_OCR)

## Enable / rollback

```env
INTERNAL_OCR_PROCESSING_ENABLED=false   # default OFF
CODE_SCAN_PROCESSING_ENABLED=false      # independent
```

| Mode | Flag | Snapshotted strategy |
|------|------|----------------------|
| INTERNAL_OCR | true | `INTERNAL_OCR` |
| INTERNAL_OCR | false + pipeline on | `LEGACY_LLM_TEMPORARY` |
| INTERNAL_OCR | false + pipeline off | `LEGACY_LLM` |

Immutable snapshot at job start (`engine_params_json.identification_execution`):

- `requested_mode`, `executed_strategy`, `reason`, `feature_flag_state`, `ocr_config`, `client_rules`
- Retries **copy** this snapshot; they do not re-read live env.

## Engine

Tesseract via `pytesseract` (subprocess timeout).

| Runtime | Where Tesseract must be installed |
|---------|-----------------------------------|
| Local `./dev.sh` | Host: `brew install tesseract tesseract-lang` (see `backend/README.md`) |
| OpenCloud DEV (`docker-compose` `api`) | `backend/Dockerfile` — `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng` (on-demand workers run in this container) |
| Dedicated worker image | `backend/Dockerfile.worker` — same packages + build-time verify |

Missing binary is a per-asset `FAILED_TECHNICAL` (`INTERNAL_OCR_ENGINE_UNAVAILABLE`), not an uncaught process crash.

## Client rules (minimal, not Phase 6 admin)

- Default: labeled `codigo` / article / product before bare EAN.
- `INTERNAL_OCR_EAN_FIRST_CLIENT_IDS=<uuid>,...` → EAN-first for those clients only (MASOL-style without hardcoding names).
- Do **not** set global `INTERNAL_OCR_PREFER_EAN_AS_INTERNAL_CODE=true` in production for all clients.

## Confidence

`INTERNAL_OCR_MIN_AGGREGATE_CONFIDENCE` (optional 0–100): below threshold → `PENDING_MANUAL_REVIEW` (`LOW_OCR_CONFIDENCE`), **not** auto-persist.

## Evidence

Stored on `ImageProcessingResult.evidence` (hashes, variant metadata, confidence). No dedicated SQL evidence table in `0055` (avoid dead tables).

## Concurrency

Keep `MAX_INTERNAL_IMAGE_PROCESSING_CONCURRENCY=1` until SQL concurrency is validated.
