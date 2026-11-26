# DIN-508 Phase 2 — Performance validation

All figures from **measured** `docker stats` during `run_poc_validation.sh` (2026-11-26, macOS Docker, synthetic 640×360 stream). Not production hardware.

## MediaMTX container (`limits: 512MiB`, `1 CPU`)

| State | CPU % | RAM |
|-------|-------|-----|
| Idle (no publisher) | 0.00% | **6.8 MiB** |
| 1 publisher + 1 HLS reader | 0.00% | **7.9 MiB** |
| 1 publisher + 3 HLS fetches | 0.00% | **10.4 MiB** |
| 1 publisher + 5 HLS fetches | 0.00% | **10.6 MiB** |
| Dual publish A+B + load | 0.76% | **10.9 MiB** |

## Network (cumulative docker NET I/O at snapshot)

| Scenario | NET I/O (approx.) |
|----------|-------------------|
| Dual channel + viewers | **698 kB / 51.5 kB** (in/out) |

## Stream bitrate (synthetic)

From HLS `#EXT-X-STREAM-INF`: **~270 kbps** average bandwidth declaration (FFmpeg veryfast test pattern).

## Timings

| Metric | Value |
|--------|-------|
| Time to first HLS 200 | **1st attempt** (~5 s after publish start in script) |
| Full validation elapsed | **~33 s** (multi-scenario sequential) |
| MediaMTX restart | Container healthy within **~15 s** (`--version` healthcheck) |

## Backend isolation

`backend_health_http=200` before and after MediaMTX restart in same run — no coupling observed.

## Estimates vs measurements

| Item | Status |
|------|--------|
| RAM/CPU above | **Measured** |
| DJI uplink / 1080p load | **Not measured** (pending physical) |
| WebRTC CPU | **Not evaluated** (disabled) |