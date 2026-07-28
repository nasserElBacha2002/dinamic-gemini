# Phase 3 corrections — decision summary

## Decisions

1. **Serialize scan before upload:** `preparePhoto` awaits `LocalCodeScanStrategy.execute` while photo stays `preparing` with `upload_size=null`; only then sets `queued` + size.
2. **Native ML Kit:** `suspendCancellableCoroutine` + mutex (max 1 op); `LoadedScanImage.close` after Task settle; no CountDownLatch.
3. **Shadow compare:** never persist `NOT_COMPARABLE`; emit `comparison_mapping_unavailable`; keep `compare_result` null.
4. **Handoff:** removed `active|paused → review|uploading`; `finalizeCaptureForUpload()` shared by `finish`/`completeReview`.
5. **Fingerprints:** SHA-256 (pure TS); prepared file bytes when readable.
6. **PLAIN v1.1:** reject URL/WIFI/email/JSON/multiline free text on **server + mobile**.
7. **Flags:** removed unused `mobileLocalCodeScanDebugMetrics` and `LOW_MEMORY`.
8. **Metrics report:** removed empty metrics markdown from audit (no invented numbers).

## Limitations (not claiming IMPLEMENTED)

- Samsung S10+ matrix **not executed**
- Real ML Kit decode instrumented tests limited (concurrency + close pattern unit tests)
- Bitmap fallback path covered by `LoadedScanImage` API + forceBitmapFallback; full Robolectric decode deferred
- Mapped shadow compare still pending a reliable API
