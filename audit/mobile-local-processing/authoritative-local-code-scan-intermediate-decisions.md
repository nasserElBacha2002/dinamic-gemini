# Authoritative local CODE_SCAN — intermediate phase decisions

## Decision summary

1. **Authority**: Operator-confirmed local CODE_SCAN is authoritative. Backend validates, versions, and persists; it does not re-scan those assets when skip flag is on.
2. **Persist timing**: PUT ingest stores versioned rows in `authoritative_local_code_scan_results`. Final position write happens at `/process` via `ApplyAuthoritativeLocalResultsService` → existing `ProcessingResultPersister` (one image → one position).
3. **Skip remote CODE_SCAN**: After apply, asset state is `RESOLVED` with `last_strategy=LOCAL_AUTHORITY` / `error_code=RESOLVED_BY_LOCAL_AUTHORITY`. Eligible loop skips terminal assets.
4. **Phase 5 reconciliation**: Deprecated for productive path. Auto-enqueue skipped when `SERVER_AUTHORITATIVE_LOCAL_CODE_SCAN_INGEST=true`. Tables retained read-only; flags remain default false.
5. **No third parallel flow**: Reuses position UoW / coverage uniqueness; no silent overwrite of historical versions.

## Limitations

- Live SQL Server migration + concurrency not executed in this environment.
- Full Android/gradle and E2E aisle flows not run.
- Explicit SERVER_REPROCESS UI/job remains a follow-up (orchestrator skip path ready; reprocess action not fully productized).
- Performance metrics (capture→confirm, remote CODE_SCAN reduction) not measured in this run.
- Flags default **false** — production behavior unchanged until explicitly enabled.
