# Findings resolution matrix (Phase 3)

| Phase 2 / audit item | Phase 3 resolution |
|----------------------|------------------|
| authHTTP → FastAPI | `/api/internal/mediamtx/auth` + `MEDIAMTX_HTTP_AUTH_SECRET` |
| Public share grants | `aisle_live_view_grants` + `/api/public/live/{token}` |
| No aisle row required | Prepare by aisle code; optional `aisle_id` in response |
| No global operator creds | Per-channel derived publish/read + per-grant view user |
| Second publisher blocked | MediaMTX `overridePublisher: no` (unchanged Phase 2 default) |
| Inventory isolation | `InventoryAccessPolicy` on all private routes |