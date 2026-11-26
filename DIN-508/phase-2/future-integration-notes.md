# DIN-508 Phase 2 — Future public / FastAPI integration (notes only)

No product code implemented in Phase 2.

## Consumption patterns

| Consumer | Phase 3 direction |
|----------|-------------------|
| Internal authenticated viewer | FastAPI validates JWT + inventory scope → issues short-lived HLS Basic creds or JWT (`authMethod: jwt`) scoped to one `live/{inv}/{slug}` path |
| Public share link | Grant row (token hash) → public route resolves grant → playback ticket only; never expose publish password |

## HLS protection

- Playlist **and** `.ts` segments must require the same auth (otherwise direct segment URL bypass).
- Options: MediaMTX path permissions + credentials on every request; or Nginx `auth_request` to FastAPI for `/live/` prefix.

## MediaMTX ↔ FastAPI

- **HTTP auth** (`authHTTPAddress`): POST user/pass/action/path; map to grants table + aisle slug resolver.
- **JWT auth**: embed `mediamtx_permissions` claim; JWKS from FastAPI or shared signer.
- Publish for DJI: mint per-channel publish user/pass or single-use query params at grant creation time.

## Nginx (minimal)

- TLS termination
- `location /live/` proxy_pass to MediaMTX HLS
- Optional `auth_request /api/v3/internal/mtx-auth` for segment gating
- RTMP may stay on dedicated port or `nginx-rtmp` module if TLS required

## Credential lifecycle

- Static internal users (POC): revoke = regenerate config + reload.
- Production target: TTL on JWT + periodic playlist refresh in player; active viewers may play until segment cache ends after revoke.