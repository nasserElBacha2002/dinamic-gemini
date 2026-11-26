# Streaming integration validation (Phase 3)

| Check | Result |
|-------|--------|
| Channel identity parity (`test_channel_identity`) | Pass (7 tests) |
| MediaMTX auth separation publish/read/grant | Pass (`test_mediamtx_auth_service`) |
| Migration 0112 shape | Pass (`test_migration_0112_live_stream`) |
| Backend unit suite (live_stream + migration) | 7 passed |
| Full RTMP→HLS E2E with authHTTP in this run | Not executed (requires MediaMTX + backend stack running) |

Operator rerun:

```bash
export MEDIAMTX_AUTH_HTTP_URL=http://127.0.0.1:8000/api/internal/mediamtx/auth
export LIVE_STREAM_ENABLED=true
cd infrastructure/din-508-mediamtx && python3 scripts/render_mediamtx_config_phase3.py
```