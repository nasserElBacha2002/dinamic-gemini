# DIN-508 Phase 2 — RTMP / HLS validation

## Synthetic source

- FFmpeg `testsrc` 640×360 @ 15fps + AAC tone
- Codecs: H.264 + AAC (no server-side transcode)

## Checklist (automated script)

| # | Case | Executed | Outcome |
|---|------|----------|---------|
| 1 | Start RTMP publish | Yes | OK with query auth |
| 2 | MediaMTX receives stream | Yes | Log: `is publishing to path 'live/...'` |
| 3 | HLS playback | Yes | `index.m3u8` HTTP 200, `#EXTM3U` |
| 4 | Multiple viewers | Yes | Parallel curl 1/3/5 — see performance doc |
| 5 | End publish | Yes | FFmpeg `-t` duration |
| 6 | Restart same channel | Yes | Second publish on same path |
| 7 | Abrupt publisher stop | Yes | `kill -9` then republish |
| 8 | Recovery after interrupt | Yes | HLS 200 after republish |
| 9 | Two channels parallel | Yes | A + B concurrently |
| 10 | Unauthorized pub/read | Yes | Rejected / 401 |

## Sample playlist (sanitized run)

```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-INDEPENDENT-SEGMENTS
#EXT-X-STREAM-INF:...CODECS="avc1.640016,mp4a.40.2",RESOLUTION=640x360,FRAME-RATE=15.000
```

## Player

Open `infrastructure/din-508-mediamtx/poc/hls-viewer.html` locally; use viewer basic-auth credentials and:

`http://127.0.0.1:8888/<path>/index.m3u8`

## Latency (approximate, synthetic)

- `hlsSegmentDuration: 1s`, `hlsSegmentCount: 7`
- First playlist often available within **~5 s** after publish start (measured by retry loop in script)
- End-to-end glass-to-glass not measured (no browser clock sync); expect **~4–12 s** HLS typical for this segment config

WebRTC **not** implemented (HLS sufficient for POC scope).