# Mobile Observability Phase 0 — Test Report

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`

## Unit tests

Command:

```bash
cd mobile && npm run test:core -- --testPathPattern='observabilityPhase0|featureFlags'
```

Coverage (`tests/observabilityPhase0.test.ts`):

- monotonic duration
- compression ratio
- network type normalization
- error normalization
- NoOp reporter
- Safe reporter (inner throw does not propagate)
- Flagged kill switch
- sanitize / sensitive key strip
- baseline p50/p95 aggregation

Result: **PASS**

Also updated:

- `featureFlags.test.ts` — `uploadObservabilityEnabled`
- `databaseMigrations.test.ts` / `fase2UploadCore.test.ts` — migration v5

## Integration / service regression

```bash
cd mobile && npm test && npm run typecheck
```

- Services (capture, processing, operational flow, api client): **PASS** (67)
- Integration migrations: **PASS** (5)
- Core: **PASS** (105)
- `tsc --noEmit`: **PASS**

Explicit non-regression intent verified by test suite (same process/upload contracts exercised without changing assertions on endpoints/body): no process/upload API signature changes; observability is optional constructor/options only.

## Manual device tests (Samsung S10+)

| Scenario | Executed | Result |
| -------- | -------- | ------ |
| 20 images Wi-Fi | No | — |
| 50 images Wi-Fi | No | — |
| 20 images cellular | No | — |
| 50 images cellular | No | — |
| Connection loss during upload | No | — |
| App reopen with pending queue | No | — |
| Temporary HTTP error | No | — |
| HEIC image | No | — |
| Large JPEG | No | — |

**Real p50/p95 numbers:** not available in this run.

How to collect on device:

1. Build release with `DINAMIC_FLAG_UPLOAD_OBS=1` (default).
2. Run scenarios above.
3. Open Diagnóstico → “Exportar baseline observabilidad” (or full diagnostic JSON `observabilityBaseline`).
4. Record prepare_ms / upload_ms / bytes / retries / capture_to_* from the JSON.

## Limitations of the environment

- No attached Samsung S10+ or release APK exercise in the agent environment.
- First-result metric may be approximated (see implementation report).
- Do **not** claim upload speedups from Phase 0 — measurement only.
