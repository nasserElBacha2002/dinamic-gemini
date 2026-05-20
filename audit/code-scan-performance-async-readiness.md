# Code scan performance and async readiness (Phase 6C)

**Decision:** `SYNC_REMAINS_ACCEPTABLE`

**Date:** 2026-05-20

## Current safeguards (implemented)

| Control | Location | Notes |
|--------|----------|--------|
| Max assets per run | `code_scan_max_assets_per_run` in settings | Enforced before scan loop |
| Max decoded payload length | `code_scan_max_decoded_payload_length` | Per detection normalization |
| Per-asset error isolation | `RunAisleCodeScanUseCase` | Storage read / decode / scanner failures skip asset, continue run |
| No parallel bulk image loading | Sequential `for asset in assets` | One image in memory at a time |
| Scanner unavailable → 503 | `CodeScanScannerUnavailableError` | Structured API error |
| Run performance metadata | `metadata_json.performance` | `duration_ms`, `assets_per_second` after each run |

## Configuration reference

- Default max assets per run: see `env_settings.grouped_settings` (`code_scan_max_assets_per_run`).
- Sync HTTP endpoint: `POST .../code-scans/run` (no worker / LLM).

## Risk assessment

| Risk | Assessment |
|------|------------|
| HTTP timeout on large aisles | **Low–medium** while asset count stays under configured max; typical retail aisle photo counts are below default cap |
| Memory spikes | **Low** with sequential reads; largest risk is single very large image bytes in memory |
| CPU (pyzbar) | **Medium** for many images; linear with asset count |
| DB write volume | **Low**; one run + N detection rows per scan |

## Manual QA guidance (local)

1. Run scan on an aisle with 5–20 photos; note drawer completion time.
2. Inspect latest run `metadata_json.performance.duration_ms` via list endpoint or DB.
3. Confirm `assets_per_second` is stable and non-negative.
4. Repeat with one corrupt/unreadable asset; run should complete with warnings, not 500.

## When to migrate to async

Recommend **async next** (`ASYNC_RECOMMENDED_NEXT`) only if operations routinely exceed:

- Configured `code_scan_max_assets_per_run`, or
- ~60–90s wall-clock in production (proxy: `duration_ms` > 90_000 with full asset batch), or
- Reverse-proxy timeout below observed scan duration.

**Async required before production** (`ASYNC_REQUIRED_BEFORE_PRODUCTION`) is **not** indicated by current design while limits and per-asset isolation remain enforced.

## Future async design (not implemented)

- `job_type = code_scan` on existing job table or lightweight scanner worker branch
- States: `queued` → `running` → `completed` / `failed`
- `CodeScanDrawer` polls run status (reuse latest-run model)
- No LLM, prompts, or `V3JobExecutor` pipeline changes
- Matching still runs after scan completes (same as sync today)

## Out of scope for Phase 6C

- Implementing async worker
- Changing inventory export collector
- Changing review or quantity write paths
