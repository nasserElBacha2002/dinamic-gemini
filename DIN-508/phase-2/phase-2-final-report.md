# DIN-508 Phase 2 — Final report

## Closure status

**`POC_IMPLEMENTED_PENDING_PHYSICAL_VALIDATION`**

## 1. Implemented

- Isolated Docker Compose stack for MediaMTX 1.11.3 (RTMP + HLS, no transcode)
- Per-channel publish vs read credentials (internal auth)
- Deterministic channel paths `live/{inventory_id}/{slug}` (slug from inventory + trimmed aisle code)
- FFmpeg validation script + minimal HLS HTML player
- Read-only SQL collation probe for `aisles.code`
- Evidence under `DIN-508/phase-2/`

## 2. Tests actually run

| Test | Result |
|------|--------|
| `run_poc_validation.sh` | Pass (RTMP/HLS/security scenarios) |
| SQL `run_sql_collation_probe.py` | Pass (read-only) |
| Backend `/health` during MediaMTX ops | 200 |

## 3. Key results

- RTMP publish + HLS read **functional** with per-path ACLs
- Unauthorized publish/read **rejected**
- Cross-channel credential isolation **confirmed**
- Resource use **low** (<11 MiB RAM synthetic load)
- No inventory pipeline / API code changes

## 4. Files modified (repo)

| Path | Change |
|------|--------|
| `infrastructure/din-508-mediamtx/**` | **Added** — POC stack + scripts |
| `DIN-508/phase-2/**` | **Added** — evidence + reports |
| `.gitignore` | **Updated** — ignore POC `.env` + `generated/` |

## 5. Phase 1 risks resolved

| ID | Resolution |
|----|------------|
| R1 Collation | CI collation measured; channel slug avoids raw special chars |
| No MediaMTX in repo | POC stack added, isolated |
| Global publish secret | Replaced by per-channel internal users (POC scope) |

## 6. Phase 1 risks still open

| ID | Notes |
|----|-------|
| R4 Public RTMP / NAT | Not deployed; local ports only |
| R5 HLS direct access | Basic auth works; future grants/JWT still needed for public links |
| R7 DJI reconnect | Requires field test |
| R2 RC2 720p | Not validated |

## 7. Is HLS enough?

**Yes for POC and likely for first production iteration** (operator + public viewer with higher latency acceptable). WebRTC deferred unless field latency fails acceptance.

## 8. Physical test from DJI Fly

See `physical-dji-validation-guide.md`. Use derived RTMP URL with publish credentials; verify via `poc/hls-viewer.html`.

## 9. Enough evidence for Phase 3?

**Yes**, for backend grants, HTTP/JWT auth adapter, and edge TLS — **after** operator completes DJI URL-format check. Phase 3 should **not** assume DJI accepts query auth without field confirmation.

## 10. Future public + internal viewers (design note)

- **Internal:** authenticated app requests playback ticket → Basic/JWT toward MediaMTX path
- **Public:** grant token in FastAPI + short-lived HLS credentials; Nginx `auth_request` or signed segment URLs
- Segment URLs without auth leak content — Phase 3 must gate playlist **and** segments

**Stop:** Phase 2 complete; no Phase 3 implementation in this change set.