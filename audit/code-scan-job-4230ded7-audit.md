# CODE_SCAN timeout audit — Job `4230ded7-eb45-445e-bfb5-ecd2fc054a92`

## Executive summary

**CONFIRMED:** `CODE_SCAN_VARIANTS_BUDGET_SECONDS` (15s) was applied as an **asset-wide**
monotonic budget starting at `CodeScanProcessingStrategy.process()` entry — **before**
`read_image_bytes` / GCS `get_object`. Asset 1 spent ~20.15s loading ~2.3 MB from GCS;
when `decode_started` fired, `_check_timeout` failed immediately and **pyzbar never ran**.

**CONFIRMED (fix):** Decode/variants budget now starts **after** `source_loaded`, covering
image preparation + barcode variants only. Public `error_code` remains `CODE_SCAN_TIMEOUT`
with `timeout_phase=decode` diagnostics.

**LIKELY:** GCS latency for ~2.2 MB PNGs (~10–20s) is abnormal; investigate separately.
Do **not** paper over it by raising the variants budget.

**UNVERIFIED:** Exact PNG pixel dimensions / host CPU saturation during the original run.

## Timeline (CONFIRMED from `processing_events`)

| timestamp (UTC) | event | asset | Δ |
|---|---|---|---|
| 21:57:47.711 | `code_scan.asset_started` | 53543709… | 0 |
| 21:58:07.860 | `asset.source_loaded` (2,312,474 B) | 53543709… | **~20,150 ms** |
| 21:58:07.879 | `code_scan.decode_started` | 53543709… | 19 ms |
| 21:58:07.960 | `code_scan.decode_failed` `CODE_SCAN_TIMEOUT` | 53543709… | 82 ms |
| 21:58:08.015 | `code_scan.asset_started` | e8cf8f4e… | — |
| 21:58:17.992 | `asset.source_loaded` (2,246,419 B) | e8cf8f4e… | **~9,977 ms** |
| 21:58:18.707 | `code_scan.decode_completed` (4 variants) | e8cf8f4e… | ~653 ms decode |
| 21:58:18.726 | `asset_finalized` `UNRECOGNIZED` | e8cf8f4e… | — |

Asset1 state: `FAILED_TECHNICAL`, `duration_ms=20288`, message `code scan exceeded 15s budget`.  
Asset2 state: `UNRECOGNIZED` / `NO_CODE_SYMBOL_FOUND`, `duration_ms=10736`.

## Job configuration (CONFIRMED)

- `identification_mode` / `execution_strategy`: `CODE_SCAN`
- `processing_mode`: `CODE_SCAN_ONLY` (not AUTO)
- `external_fallback.fallback_enabled`: **false**
- Variants budget: **15s** (default; no env override observed)
- Sequential assets (`MAX_IMAGE_PROCESSING_CONCURRENCY` default 1)

## Asset 1 analysis

| Phase | Duration | Confidence |
|---|---|---|
| source_load | ~20,150 ms | CONFIRMED |
| image_prepare | 0 ms (never reached) | CONFIRMED |
| decoder | 0 ms (never reached) | CONFIRMED |
| budget remaining at decode start | exhausted (~−5s vs 15s) | CONFIRMED |

Root fail: **mis-scoped timeout**, not a hanging decoder.

## Asset 2 analysis

| Phase | Duration | Confidence |
|---|---|---|
| source_load | ~9,977 ms | CONFIRMED |
| decode (4 variants) | ~653 ms | CONFIRMED |
| outcome | UNRECOGNIZED / no symbols | CONFIRMED |

Shows decoder returns quickly when budget remains after load.

## Timeout implementation (before)

```text
asset_started → started=monotonic()
read_image_bytes (GCS)          ← consumed budget
source_loaded
decode_started                  ← misleading
_scan_with_variants(started)
  _check_timeout → CODE_SCAN_TIMEOUT
```

## Timeout implementation (after fix)

```text
asset_started
source_load_*
source_loaded (source_load_ms)
decode_budget_started_at=monotonic()   ← CODE_SCAN_VARIANTS_BUDGET_SECONDS
decode_started (timeout_scope=decode)
prepare_* + decoder variants
```

Budget covers: PIL prepare / EXIF / resize / rotations / pyzbar variants.  
Budget does **not** cover: storage I/O.  
Budget is **cooperative** (between steps); not a hard interrupt of native pyzbar.

## Vision fallback

**CONFIRMED unchanged:** `CODE_SCAN_TIMEOUT` ∈ `TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES`.  
This job was `CODE_SCAN_ONLY` with fallback disabled anyway.

## Recommended follow-ups

1. Separate GCS latency investigation (not variants budget).
2. Optional UI surfacing of `timeout_phase` / `source_load_ms` from event metadata.
3. Optional future `source_load_timeout` as a **distinct** error code (not `CODE_SCAN_TIMEOUT`).

## Remaining unknowns

- Why GCS took 10–20s for ~2.2 MB (**LIKELY** network/storage; **UNVERIFIED** cause).
- Pixel dimensions of ChatGPT-generated PNGs (**UNVERIFIED**).
