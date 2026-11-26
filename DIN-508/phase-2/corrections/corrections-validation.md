# DIN-508 Phase 2 — Corrections validation report

**Closure:** `PHASE_2_CORRECTED_PENDING_PHYSICAL_VALIDATION`

## Findings corrected

| # | Finding | Fix |
|---|---------|-----|
| 1 | `A01` / `a01` could diverge in channel slug | `canonical_aisle_code_for_channel`: strip + uppercase (CI alignment); 8 unit tests |
| 2 | Docker healthcheck only ` --version` | `Dockerfile` adds busybox `wget`; probe Control API on `127.0.0.1:9997` |
| 3 | Git dumps inside `DIN-508/phase-2/` | Removed `phase-2-diff*.txt`; gitignored; corrections artifacts under `corrections/` only |
| 4 | HLS segment bypass not tested | Segment `.ts`: auth 200 / no-auth **401** |
| 5 | Concurrent dual publisher | Tested; `overridePublisher: yes` explicit; playlist stays 200 |
| 6 | Health stop/recover | `docker compose stop` → **unhealthy**; `start` → **healthy** |
| 7 | RTMP cleartext | Documented in `streaming-security-validation.md` |

## Commands executed

```bash
.venv/bin/pytest infrastructure/din-508-mediamtx/tests/ -q --tb=short   # 8 passed
cd infrastructure/din-508-mediamtx && docker compose build && ./scripts/run_poc_validation.sh
```

## Key measured results

- `segment_noauth_http=401`, `segment_auth_http=200`
- `viewer_a_on_b_http=401` (cross-channel read)
- `concurrent_publish_playlist_http=200` with dual FFmpeg publishers
- `health_recover=healthy` after stop/start
- `backend_health_http=200` throughout

## Decisions

- **Canonical aisle code:** `strip()` + `upper()` for Latin inventory codes under `SQL_Latin1_General_CP1_CI_AS`; accents not auto-folded (documented residual).
- **Healthcheck:** readiness via loopback API only; active stream checked on host, not in Docker health.
- **Concurrent publish:** MediaMTX default `overridePublisher: yes` retained explicitly (second publisher replaces first).

## Residual risks

- DJI Fly RTMP URL + query auth **not field-validated**
- RTMP without TLS on POC port 19350
- Full Unicode collation edge cases not exhaustively proven in Python

## Files modified (implementation)

- `infrastructure/din-508-mediamtx/scripts/channel_id.py`
- `infrastructure/din-508-mediamtx/Dockerfile` (new)
- `infrastructure/din-508-mediamtx/docker-compose.yml`
- `infrastructure/din-508-mediamtx/scripts/render_mediamtx_config.py`
- `infrastructure/din-508-mediamtx/scripts/run_poc_validation.sh`
- `infrastructure/din-508-mediamtx/tests/*`
- `infrastructure/din-508-mediamtx/scripts/run_corrections_validation.sh` (new)
- `.gitignore`
- `DIN-508/phase-2/*.md` (docs updates)

## Evidence files (this folder)

- `implementation-corrections-tests.txt` — pytest output
- `implementation-corrections-tests-streaming.txt` — sanitized streaming run (from `run_poc_validation.sh`)
- `implementation-corrections-status.txt`, `-diffstat.txt`, `-diff.txt` — git working tree (gitignored patterns may apply at repo root; copies kept here for review)