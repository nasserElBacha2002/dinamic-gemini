# Production / OpenCloud deployment validation

**Target:** DEV OpenCloud (`develop` branch, `/opt/dinamic/dinamic-gemini`).

## Inspected (repo)

| Item | Finding |
|------|---------|
| Backend deploy | GHA `deploy-dev-opencloud-backend.yml` — SSH port **37783**, `docker-compose` **api** only |
| Frontend deploy | Vercel Git integration, production branch **develop** |
| DB migrations | `dev_deploy_db_migrate.sh` after container up; **0113** additive columns |
| MediaMTX | Isolated compose `infrastructure/din-508-mediamtx/`; API **127.0.0.1:9997** in POC |
| Rollback | `git reset` on server + prior image; migration down `0113_* .down.sql` if needed |

## VPS steps (operator — not executed by agent)

1. `git pull` / deploy via GHA on `develop`.
2. Confirm migration `0113` applied (`db migrate status`).
3. MediaMTX: render Phase 3 config, `docker compose up -d` on isolated network.
4. Root `.env`: `LIVE_STREAM_ENABLED=true`, `LIVE_STREAM_MEDIAMTX_API_URL` reachable from **api** container (host gateway), `MEDIAMTX_HTTP_AUTH_SECRET`, RTMP/HLS public bases, `LIVE_STREAM_PUBLIC_LINK_BASE_URL`.
5. Nginx: HLS under app domain; **do not** expose `:9997` publicly.
6. `curl` backend `/health`; optional public `/health` via `DEV_BACKEND_URL` secret in GHA.

## Smoke (post-deploy)

| Check | Status |
|-------|--------|
| Backend `/health` | Pending post-push |
| `LIVE_STREAM_ENABLED=false` inventory unchanged | Design preserved |
| RTMP publish authorized | Pending |
| HLS HTTPS playback | Pending |
| Public `/live/{token}` | Pending |
| Stop + prepare | Pending |

## Agent limitation

No `DEV_HOST` / SSH key in local environment; deploy validation continues via **GitHub Actions** after merge to `develop`.