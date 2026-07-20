# Aisle identification — Phase 4 (INTERNAL_OCR per-image processing)

## Goal

Replace the temporary `INTERNAL_OCR → LEGACY_LLM_TEMPORARY` bridge with a **real local OCR**
execution strategy (Tesseract via `pytesseract`) that extracts `internal_code` + `quantity`
from each aisle photo — **without** Gemini/OpenAI/Claude fallback.

## Enable

```bash
INTERNAL_OCR_PROCESSING_ENABLED=true
```

Default is **`false`**. When disabled, selecting `INTERNAL_OCR` still snapshots
`LEGACY_LLM_TEMPORARY` (Phase 1 behaviour).

## Engine

| Item | Value |
|------|-------|
| Engine | Tesseract (`INTERNAL_OCR_ENGINE=tesseract`) |
| Python package | `pytesseract==0.3.13` |
| Native deps (worker image) | `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng` |
| Languages | `INTERNAL_OCR_LANGUAGE=spa+eng` |

### Timeout honesty

Each Tesseract call uses pytesseract's **subprocess timeout** (process is killed). The strategy
also enforces a wall-clock budget between variants. Soft logical timeouts that leave work
running are not used.

### Why Tesseract

CPU-only slim worker, Spanish printed labels, small Docker footprint vs PaddleOCR/EasyOCR,
deterministic confidence scores for audit/manual review.

## Architecture

```text
V3JobExecutor
  └─ execution_strategy == INTERNAL_OCR
        → _run_internal_ocr_path
            → InternalOcrProcessingStrategy
                → OcrImagePreprocessor (bounded variants)
                → InternalLabelReader (Tesseract)
                → OcrFieldExtractor
                → OcrResultNormalizer (+ client field priority)
            → ProcessingResultPersister (same as CODE_SCAN)
            → CodeScanJobOutcomePolicy
```

## Client rules (no hardcoding)

`INTERNAL_OCR_PREFER_EAN_AS_INTERNAL_CODE=true` (default) makes EAN win over ARTICULO/PRODUCTO
for `internal_code`. This covers MASOL-style EAN→code behaviour without naming clients in the
orchestrator.

## Env vars

See `.env.example` Phase 4 block. Key flags:

- `INTERNAL_OCR_PROCESSING_ENABLED` (default false)
- `INTERNAL_OCR_MAX_VARIANTS` (default 3)
- `INTERNAL_OCR_TIMEOUT_SECONDS` (default 20)
- `INTERNAL_OCR_MAX_IMAGE_DIMENSION` (default 2048)
- `MAX_INTERNAL_IMAGE_PROCESSING_CONCURRENCY` (default 1; independent of CODE_SCAN)

## Rollback

Set `INTERNAL_OCR_PROCESSING_ENABLED=false`. New jobs with `INTERNAL_OCR` mode again use
`LEGACY_LLM_TEMPORARY`. Historical jobs keep their immutable `execution_strategy` snapshot.

Migration `0055` is additive (CHECK widen + optional evidence table); no destructive rollback
required for data.

## Out of scope (Phase 5+)

External LLM fallback per asset, CODE_SCAN→OCR→external chains, full frontend redesign.
