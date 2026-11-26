# DIN-508 Phase 3 — corrections validation

Generated: 2026-11-26 (UTC)

## Summary

| Area | Code correction | Automated proof | Runtime / E2E proof |
|------|-----------------|-----------------|---------------------|
| 1. Revoke grant inventory scope | Applied | **Pass** (unit) | Not required |
| 2. MediaMTX authHTTP ↔ FastAPI | `mtx_key` query + header fallback | **Pass** (unit route + service) | **Pending** (curl + FFmpeg) |
| 3. HLS player lifecycle | Applied | **Pass** (frontend build + typecheck) | **Pending** (manual multi-flight) |
| 4. Public link security | `Cache-Control: no-store`, auth service deny when disabled | **Partial** (unit: grant expiry, disabled) | **Pending** (revoked viewer + segment fetch) |
| 5. Concurrent prepare / aisle association | Idempotent prepare; resolver by aisle code | **Pass** (unit idempotent + channel identity) | **Pending** (SQL aisle row after prepare) |

## Executed

### Backend unit (`tests/unit/live_stream`)

- **12 passed** — see `implementation-corrections-tests.txt`
- Covers: channel identity isolation, MediaMTX auth decisions (publish/read, cross-path, expiry, disabled), authHTTP route (`mtx_key` / missing key), revoke grant scoped by `inventory_id`, concurrent prepare idempotency

### Frontend

- `npm run build` — **OK** (dist secrets scan OK)
- `npm run typecheck` — **OK** (prior run in correction pass)

### MediaMTX authHTTP live probe

- **SKIP** — `MEDIAMTX_HTTP_AUTH_SECRET` not set in shell / root `.env` at validation time

### FFmpeg RTMP + HLS playback

- **SKIP** — `RUN_FFMPEG_SMOKE` not set; operator must supply channel credentials and Phase 3 `mediamtx.yml`

## Pending (operator — deployment validation)

1. Set in root `.env`: `LIVE_STREAM_ENABLED=true`, `MEDIAMTX_HTTP_AUTH_SECRET`, RTMP/HLS base URLs, `MEDIAMTX_AUTH_HTTP_URL` (see `.env.example` and `infrastructure/din-508-mediamtx/.env.example`).
2. Regenerate MediaMTX config: `python infrastructure/din-508-mediamtx/scripts/render_mediamtx_config_phase3.py` → restart MediaMTX with `authMethod: http` and `authHTTPAddress` including `mtx_key`.
3. Re-run: `MEDIAMTX_HTTP_AUTH_SECRET=… bash infrastructure/din-508-mediamtx/scripts/run_phase3_corrections_validation.sh`
4. Optional E2E: `RUN_FFMPEG_SMOKE=1` with documented publish path/credentials; verify HLS read with backend-authorized credentials; retry after revoke/expiry on public token.

## Not in scope (per DIN-508 close)

Firmware, mobile app, scan pipeline, new recording/WebRTC/IA features, production deploy, Phase 4.

## Closure recommendation

**`PHASE_3_CORRECTED_READY_FOR_DEPLOYMENT_VALIDATION`** — review fixes are implemented and covered by focused unit tests; stack-level RTMP/HLS and live authHTTP probe remain operator validation.