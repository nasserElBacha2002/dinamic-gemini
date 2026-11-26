# Phase 3 code review → corrections resolution matrix

| # | Review finding | Resolution | Evidence |
|---|----------------|------------|----------|
| 1 | `revoke_public_grant` not scoped by inventory | `LiveStreamRepository.revoke_view_grant(grant_id, inventory_id=…)`; SQL `WHERE id AND inventory_id`; use case passes inventory from route | `test_revoke_grant_inventory_scope.py` |
| 2 | MediaMTX 1.11.x authHTTP cannot send `X-MediaMTX-Auth-Secret` | `render_mediamtx_config_phase3.py` appends shared secret as `mtx_key` query on `authHTTPAddress`; route accepts header **or** `mtx_key` | `test_mediamtx_auth_http_route.py`, `render_mediamtx_config_phase3.py` |
| 2b | Live auth when feature disabled | `MediaMtxAuthService` returns deny when `enabled=False` | `test_mediamtx_auth_disabled.py` |
| 3 | HLS player unstable callbacks / reconnect / cleanup | `HlsLivePlayer`: stable `onPresenceChange` ref; hls.js network recovery; native Safari credentialed URL; destroy on unmount | `HlsLivePlayer.tsx`, frontend build |
| 4 | Public playback cacheable / stale after revoke | `Cache-Control: no-store` on public playback response; grant expiry/revoke enforced in auth service | `public_live.py`, `test_mediamtx_auth_service.py` (expired grant) |
| 4b | Secrets in logs | No change required beyond existing patterns; validation script does not echo secrets | `run_phase3_corrections_validation.sh` |
| 5 | Concurrent prepare duplicates credentials | `prepare_channel` reuses existing publish/read usernames when channel row exists | `test_prepare_channel_idempotent.py` |
| 5b | Aisle created after prepare | Channel keyed by `inventory_id` + aisle **code** via resolver (unchanged creation/import logic) | `live_stream_aisle_channel_resolver.py`, `test_channel_identity.py` |
| 6 | API test suite wiped DB / SSL | MediaMTX authHTTP route tests moved to isolated unit mini-app | `test_mediamtx_auth_http_route.py` (unit); removed conflicting API test |

## Runtime validation still outstanding

| Finding aspect | Status |
|----------------|--------|
| Real FFmpeg publish + HLS read with authHTTP | Pending operator env + MediaMTX Phase 3 config |
| Revoked public viewer cut off mid-playlist | Pending manual/E2E |
| Direct segment URL after revoke/expiry | Pending manual/E2E |
| Multi successive flights same channel (player) | Pending manual UI |