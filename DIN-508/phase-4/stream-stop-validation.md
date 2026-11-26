# Stream stop validation — Phase 4

## Design

1. Operator confirms **Cortar transmisión** in internal dialog.
2. API sets `publish_blocked_at` **before** kick (fail-closed on reconnect).
3. MediaMTX Control API kicks active `rtmpConn` publisher (best-effort if API unreachable).
4. `authHTTP` rejects new `publish` until **Preparar transmisión** clears block.
5. Read paths (internal + public grants) unchanged.

## Automated (unit-level)

| Case | Mechanism | Executed |
|------|-----------|----------|
| Block denies publish | `test_stop_transmission.py` | Prepared in repo; run via CI pytest |
| Prepare clears block | same | Prepared in repo |
| Idempotent stop | sets blocked_at again | Logic in use case |
| Kick without API | `publisher_kicked=false`, block still set | `LiveStreamMediaMtxControl` nil base URL |

## Integration (not executed this run)

- FFmpeg publisher + stop + FFmpeg reconnect denied
- DJI Fly auto-reconnect after cut
- Concurrent publishers on same path (`overridePublisher: no`)

## Manual checklist (operator)

- [ ] Live RTMP → **Cortar transmisión** → HLS ends within segment window
- [ ] DJI reconnect within 30s → publish denied (logs: `publish_blocked`)
- [ ] **Preparar transmisión** → publish succeeds again
- [ ] Public URL still works on next flight (same grant)