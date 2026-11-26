# Production security validation — DIN-508 Phase 4

| Control | Status |
|---------|--------|
| MediaMTX API bound to localhost in POC compose | Config default |
| `authHTTP` secret via header or `mtx_key` query (not logged in evidence) | Phase 3 |
| RTMP/HLS credentials derived; hashes at rest | Phase 3 |
| Public tokens: hash only in DB | Phase 3 |
| Publish block after cut (no RTMP bypass without prepare) | Phase 4 |
| Inventory-scoped v3 routes + grant scope | Phase 3 |
| Public viewer: no session; grant expiry/revoke | Phase 3 |
| `Cache-Control: no-store` on public playback | Phase 3 |

## Not validated in this run

- External port scan for 9997/1935 on VPS
- RTMPS/TLS for DJI publish path (not assumed; RTMP cleartext documented)
- Safari / mobile CSP and CORS on HLS edge

## Evidence hygiene

All Phase 4 artifacts avoid `.env`, passwords, tokens, and `mtx_key` values.