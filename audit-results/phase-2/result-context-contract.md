# Result Context Contract (Phase 2)

## Precedence

1. **Explicit `job_id`** (query/body) — validated: exists, targets the aisle, actor may access inventory.
2. Else **`aisles.operational_job_id`** — validated the same way (no silent `jobs[0]`).
3. Else **legacy** — `positions.job_id IS NULL` only.

## Non-goals

- Never treat `jobs[0]`, newest `updated_at`, or first list row as operational SoT.
- Invalid operational pointer does **not** fall back to latest job; fail or use legacy only when contract allows.

## Single resolver

`src.application.services.result_context_resolver.ResultContextResolver`

Returns `ResolvedAisleResultContext` with `job_id_for_slice`, `source` (`explicit` | `operational` | `legacy` | `audit_all`), `read_mode`, `is_legacy`.

## Frontend

`resolveBrowseRunJobIds`: URL explicit → operational (display only) → null.
`passExplicitJobIdToApi` only when URL selects a listed job; otherwise omit `job_id` so backend owns SoT.

## Consumer matrix (Phase 2 corrections)

Real call sites, checked directly against source (not aspirational). "Reuses resolver" = literally
constructs/calls `ResultContextResolver.resolve(...)`. Consumers that must match the *same slice
semantics* but cannot call the resolver directly (raw SQL, or the request shape has no optional
job override) are marked "parity-matched" with the file that encodes the duplicated predicate —
these are a known duplication risk and should be covered by `test_phase2_cross_contract_result_context.py`
whenever the parity predicate changes.

| Consumer | Resolver reuse | Explicit `job_id` | Operational pointer | Legacy (`job_id IS NULL`) | Invalid operational pointer | Cross-client explicit `job_id` |
|---|---|---|---|---|---|---|
| Positions list (`ListAislePositionsUseCase`) | Reuses resolver directly (`list_aisle_positions.py`) | Supported (`?job_id=`) | Supported | Supported | `JobDoesNotBelongToAisleError` (fail-fast, no legacy fallback) | Denied upstream by `InventoryAccessPolicy` (404, inventory not found for principal) before the resolver ever runs |
| Position detail (`GetPositionDetailUseCase`) | Reuses resolver directly (`get_position_detail.py`) | Supported | Supported | Supported | Same as positions list | Same as positions list |
| Aisle merge results (`GetAisleMergeResultsUseCase`) | Reuses resolver directly (`get_aisle_merge_results.py`) | Supported (`command.job_id`) | Supported | Supported | Same fail-fast | Same as positions list |
| Code scan detection matching (`MatchAisleCodeScanDetectionsUseCase`) | Reuses resolver directly (`match_aisle_code_scan_detections.py`) | Supported | Supported | Supported | Same fail-fast | Same as positions list |
| Aisle list / status (`list_aisles_with_status.py`) | Reuses resolver directly, always `explicit_job_id=None` | N/A (list endpoint has no per-aisle job override) | Supported | Supported | Same fail-fast | N/A (inventory-scoped list already access-checked) |
| Exports — single aisle CSV (`export_inventory_results.py`) | Reuses resolver directly | Supported (`?job_id=` on `GET …/aisles/{id}/export`, aligned with positions) | Supported | Supported | Same fail-fast | Same as positions list |
| Exports — inventory-wide business export (`export_inventory_collector.py`) | Reuses resolver directly, per aisle | `collect_inventory(...)` accepts `explicit_job_id_by_aisle: dict[aisle_id, job_id]`, but no current API route passes it — always effectively `None`/legacy-or-operational only in practice | Supported | Supported | Same fail-fast; would apply if a route ever threads the override through | N/A (inventory-scoped export already access-checked) |
| Stored asset preview — HEIC/HEIF normalized JPEG (`resolve_normalized_asset_path` in `api/routes/v3/shared.py`) | Reuses resolver directly | Supported (`?job_id=`) | Supported | Legacy has **no** per-run manifest folder → returns `None` (404 at route), not a silent slice | Same fail-fast (propagates as 4xx) | Same as positions list |
| SQL analytics (`sql_analytics_repository.py`) | **Parity-matched, not literal reuse** — `_operational_result_slice_predicate()` hardcodes `positions.job_id = aisles.operational_job_id` else `job_id IS NULL` in raw SQL | Not supported — `AnalyticsFilters` has no `job_id` field | Supported (predicate) | Supported (predicate) | Not applicable at the SQL layer (no job existence/ownership check is re-run here; relies on `aisles.operational_job_id` having been validated when it was set via `PromoteAisleOperationalJob`) | N/A (inventory/aisle scoped upstream) |
| Memory analytics (`memory_analytics_repository.py`) | **Parity-matched, not literal reuse** — inline `aisle.operational_job_id` check, same else-legacy rule (comment: "same as SQL analytics") | Not supported (same DTO) | Supported | Supported | Same caveat as SQL analytics | N/A |
| Evidence (`GetPositionCodeScanEvidenceUseCase`) | **Does not use the resolver at all** — `resolve_position()` only validates inventory/aisle/position ownership (no job-scope check); the run summary comes from `code_scan_repo.get_latest_run_by_aisle()` (latest run, **not** the operational job), but the returned `detections` are filtered by `position_id` via `list_latest_detections_by_matched_position()`, so they stay correct because the caller already obtained `position_id` from a resolver-scoped list/detail call | N/A (no per-request job override) | Not consulted for the run summary; the individual detections are implicitly scoped by `position_id` | N/A | N/A (no pointer lookup) | Denied via `InventoryAccessPolicy` before position lookup |
| Result-evidence reads (`ResultEvidenceRepository`, position/job image evidence) | **N/A by design** — addressed by `position_id` / `evidence_id`, inherited transitively from a resolver-scoped positions/detail call | Inherited via `position_id` | Inherited | Inherited | Inherited (a stale `position_id` simply 404s) | Inherited from the call that produced `position_id` |
| Review queue (review actions: confirm/correct/delete/etc., `shared/review_validation.py`) | **Does not use the resolver** — run-scoped rows require the request `job_id` to equal `positions.job_id` exactly; `aisles.operational_job_id` is explicitly *not* consulted for authorization (see module docstring) | Required when the position is run-scoped (must match `positions.job_id`, not "any listed job") | Not consulted | Legacy rows require no `job_id` | Not applicable (no pointer lookup) | Denied via `InventoryAccessPolicy` before position lookup |
| Reports / traceability / execution-log / artifacts / hybrid-report (`GET …/jobs/{job_id}/...` routes in `api/routes/v3/aisles.py`) | **N/A by design** — `job_id` is a mandatory path parameter, not an optional override; there is no implicit resolution to bypass | Always required (path param) | N/A | N/A | N/A (job existence/aisle ownership checked by the route's own job lookup, same `JobDoesNotBelongToAisleError`-style guard) | Denied via `InventoryAccessPolicy` / job-ownership check before the report is built |
| Summaries — job list markers (`ListAisleJobsUseCase`) | **N/A** — surfaces `operational_job_id` as an informational marker per job row for the frontend to highlight; does not itself select a data slice | N/A | Surfaced as metadata only | N/A | N/A | N/A |
| Stored artifacts (manifest / artifact store reads under a job) | **N/A by design** — always addressed by an explicit `job_id` + `artifact_id`, same as reports | Always required | N/A | N/A | N/A | Denied via job-ownership check |
| Mobile endpoints (capture session staging / preliminary detections) | **N/A** — these are pre-job, asset/session-scoped capture-time records; job assignment happens later (materialize → process), so there is no job slice to resolve yet | N/A | N/A | N/A | N/A | Denied via `InventoryAccessPolicy` (Phase 2 corrections, see `inventory_access_policy.py`) |

Key takeaways:

- Only 8 call sites literally construct/call `ResultContextResolver` (positions list, position detail,
  aisle merge results, code scan matching, aisle list/status, single-aisle export, inventory-wide
  export collector, HEIC/HEIF asset preview). All of them accept the same three-way precedence and
  fail fast (never fall back to legacy) on an invalid operational pointer.
- SQL and memory analytics **cannot** call the resolver (no per-request job override in
  `AnalyticsFilters`, and SQL needs a predicate, not a Python object) — they duplicate the
  operational/legacy rule instead. `test_phase2_cross_contract_result_context.py` is the guard
  against these three implementations drifting apart.
- Review queue, reports/artifacts, job-list markers, evidence, and mobile capture endpoints are
  intentionally outside the resolver's scope (different addressing model — explicit path param,
  inherited `position_id`, or pre-job record) and are documented here to make that an explicit,
  reviewed decision rather than an undocumented gap.
