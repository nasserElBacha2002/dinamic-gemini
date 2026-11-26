# DIN-508 Phase 2 — Streaming security validation

## Model (MediaMTX internal auth)

- `authMethod: internal`
- Separate users per channel for **publish** vs **read/playback**
- No default anonymous publish/read (removed global publish secret)
- API permission only from `127.0.0.1` inside container (not exposed on host)

## Tests executed (FFmpeg + curl)

Evidence: `phase-2-tests.txt`

| Scenario | Result |
|----------|--------|
| Unauthorized RTMP publish | Rejected (`authentication failed` in server logs; FFmpeg EOF) |
| Authorized RTMP publish (channel A) | OK; HLS playlist **200** with viewer basic auth |
| HLS without credentials | **401** |
| Publish to channel B with channel A publisher creds | Rejected |
| Simultaneous publishers on A and B | OK (independent paths) |
| Republication on same path after stop | OK |
| Abrupt publisher kill + republish | OK (recovery) |
| `docker compose restart mediamtx` | Container recreates; config from volume; publish works after restart |

## RTMP credential format (important for DJI / FFmpeg)

MediaMTX **1.11.3** rejected `rtmp://user:pass@host/path` from FFmpeg. **Working format:**

```
rtmp://<host>:<port>/<path>?user=<pub_user>&pass=<pub_pass>
```

HLS playback: HTTP **Basic** auth (`-u viewer:pass`) — query `user`/`pass` on HLS returned **401** in probe.

## Admin / metrics exposure

- Host ports published: RTMP + HLS only
- API `9997` not mapped to host

## Future FastAPI integration (not implemented)

MediaMTX supports `authMethod: http` and `jwt` (see upstream `mediamtx.yml` template). Recommended Phase 3 path:

1. FastAPI endpoint validates inventory/aisle scope + grant
2. Returns short-lived publish/read credentials or signed JWT with `mediamtx_permissions`
3. Nginx terminates TLS; proxies HLS with optional auth pass-through

## RTMP transport (POC limitation)

- RTMP is **cleartext** on port `19350` (`rtmpEncryption: "no"`).
- Credentials travel in the RTMP handshake/query string — vulnerable on untrusted networks.
- **RTMPS/TLS** not enabled in POC; production requires edge TLS or RTMPS before field use on public networks.

## Expiration / revocation (POC observation)

Internal static passwords remain valid until config reload/redeploy. Revoking requires re-render config + container reload. **Existing HLS viewers** keep access until credentials change and segments expire (~`hlsMuxerCloseAfter` 60s without publisher). Not tested with JWT TTL in this phase.