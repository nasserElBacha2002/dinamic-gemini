# Rollback plan — DIN-508 Phase 4

## Fast disable (no schema rollback)

1. Set `LIVE_STREAM_ENABLED=false` in server `.env`.
2. Restart backend API container.
3. MediaMTX: `docker compose stop` in `infrastructure/din-508-mediamtx` (optional).

Inventory processing and mobile unaffected.

## Backend code rollback

1. On server: `git fetch` && `git reset --hard origin/<previous-sha>`.
2. `cd backend && docker-compose build api && docker-compose up -d`.
3. Smoke `/health`.

## Migration rollback (only if necessary)

1. Take DB backup (existing ops procedure).
2. Apply `backend/src/database/migrations/versions/0113_din508_live_publish_blocked.down.sql` via project migrate tooling.
3. Do **not** drop `0112` tables if grants/credentials in use.

## Forward fix preferred

If stop/kick misbehaves, disable feature flag first; fix forward on `develop` rather than destructive schema rollback.