# DIN-508 Phase 2 — Infrastructure implementation

## Scope

Isolated MediaMTX POC under `infrastructure/din-508-mediamtx/`. **Not** merged into `backend/docker-compose.yml` (API remains on port 8000 only).

## Components

| Artifact | Purpose |
|----------|---------|
| `docker-compose.yml` | Standalone stack (`dinamic-mediamtx-poc`), network `dinamic-mediamtx-poc-net` |
| `scripts/render_mediamtx_config.py` | Renders `generated/mediamtx.yml` from local `.env` (secrets not committed) |
| `scripts/channel_id.py` | Deterministic path token `live/{inventory_id}/{sha256_slug}` |
| `scripts/run_poc_validation.sh` | FFmpeg RTMP + HLS HTTP checks + `docker stats` |
| `poc/hls-viewer.html` | Minimal HLS player (not part of React frontend) |

## Image and ports

- Base image: `bluenviron/mediamtx:1.11.3` (pinned), local `Dockerfile` adds **busybox wget** only for in-container readiness (no runtime sidecar)
- Built tag: `dinamic/mediamtx-poc:1.11.3`
- Host RTMP: `19350` → container `1935` (avoids local `1935` conflicts)
- Host HLS: `8888`
- Control API: `127.0.0.1:9997` **inside container only** (not published)
- Disabled: RTSP, WebRTC, SRT, recording, metrics, pprof, playback server

## Resources and logs

- CPU limit: `1.0`, RAM limit: `512MiB`
- json-file log driver: `max-size=10m`, `max-file=3`

## Healthcheck

| Layer | Probe |
|-------|--------|
| **Liveness/readiness (container)** | `wget --spider http://127.0.0.1:9997/v3/config/global/get` (API bound to loopback only) |
| **Service stop/recover** | `docker compose stop` → unhealthy/stopped; `start` → healthy (validation script) |
| **Active stream** | Host script: RTMP publish + HLS `200` (not part of Docker healthcheck) |

## Reproducible install

```bash
cd infrastructure/din-508-mediamtx
cp .env.example .env   # set POC_* secrets
python3 scripts/render_mediamtx_config.py
docker compose up -d
./scripts/run_poc_validation.sh
docker compose down
```

## Isolation evidence

During validation, backend `GET http://127.0.0.1:8000/health` returned **200** while MediaMTX was started, restarted, and stressed (see `phase-2-tests.txt`).