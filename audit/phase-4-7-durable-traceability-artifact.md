# Phase 4.7 — Durable Traceability Artifact

## 1. Executive summary

**Verdict:** COMPLETE

| Item | Status |
|------|--------|
| Durable `traceability_manifest.json` implemented | Yes |
| Generated from structural `result_evidence` rows | Yes |
| Includes execution image manifest + provider order | Yes |
| Fail-closed `displayable` in artifact | Yes |
| Published via existing artifact outbox (required path) | Yes |
| Required for active V3 photo canonical jobs (explicit context) | Yes |
| Deterministic hashes + JSON-safe content | Yes |
| Stable `traceability_manifest_hash` across retries | Yes |
| Static + dynamic required artifact completeness | Yes |
| Idempotent outbox registration per job/kind | Yes |
| Phase 4.6 / 4.5 / artifact regressions | Yes |
| Video traceability | No |
| Phase 4.8 started | No |

## 2. Artifact schema

**File:** `traceability_manifest.json`  
**Schema version:** `phase-4.7.traceability_manifest.v1`

| Section | Purpose |
|---------|---------|
| `execution_image_manifest` | Canonical Phase 4.3 manifest projection (null when optional/unavailable) |
| `provider_image_manifest_order` | Provider payload order with soft validation warnings |
| `result_evidence` | Structural rows from Phase 4.6 with `displayable` flag |
| `summary` | Counts by traceability status, displayability, and failure classes |
| `artifact_created_at` | Runtime generation timestamp (excluded from content hash) |
| `integrity` | SHA-256 hashes with `traceability_manifest_hash_excludes` |

## 3. Source of truth

Priority:

1. Structural `result_evidence` rows (`list_for_scope`)
2. Canonical `execution_image_manifest` from prompt composition (validated before build)
3. `provider_image_manifest_order` from run metadata (soft-validated against manifest)
4. `hybrid_report` — not used when structural rows exist

## 4. Publication flow

```text
PersistAisleResult (Phase 4.6)
  → TraceabilityArtifactService.generate_and_write()
  → traceability_manifest.json in run_dir
  → ArtifactPublicationDispatcher.register_publication_work(required_kind_overrides)
  → staging (EXACT_DURABLE_SOURCE)
  → outbox entry (artifact_kind=traceability_manifest)
  → dispatch_job publish
  → durable artifact store + manifest mark_published
  → job finalization continuation
```

**Non-outbox policy (Option A):** When `traceability_manifest` is required and `artifact_dispatcher` is unavailable, finalization fails with `ARTIFACT_SOURCE_STAGING_FAILED` and metadata `traceability_error_code=ARTIFACT_OUTBOX_REQUIRED_FOR_TRACEABILITY`. Legacy non-outbox durable upload does not publish required traceability artifacts.

## 5. Requirement semantics

Traceability manifest is required for **active V3 photo canonical jobs** when:

- `input_type == "photos"`
- `canonical_traceability_expected == True` (V3 `process_aisle` photo runs)

Requirement is **not** inferred only from manifest presence in prompt composition.

| Condition | Behavior |
|-----------|----------|
| Required + missing manifest | `TRACEABILITY_MANIFEST_MISSING` |
| Required + corrupt manifest | `TRACEABILITY_MANIFEST_INVALID` |
| Required + missing structural rows | `TRACEABILITY_EVIDENCE_MISSING` |
| Required + no artifact outbox | `ARTIFACT_OUTBOX_REQUIRED_FOR_TRACEABILITY` |
| Optional + missing manifest | Artifact generated with `execution_image_manifest=null` and warning |

## 6. Required artifact completeness

`required_kinds_published()` and `missing_required_kinds()` validate:

1. All static `REQUIRED_ARTIFACT_KINDS` (`execution_log`, `hybrid_report_json`) are present, `required=True`, and `PUBLISHED`
2. All dynamic manifest entries with `required=True` (e.g. `traceability_manifest`) are `PUBLISHED`

## 7. Stable hashing

`traceability_manifest_hash` is computed from stable sections only:

- `schema_version`, `job_id`, `inventory_id`, `aisle_id`, `run_id`, `provider`, `model_name`
- `execution_image_manifest`, `provider_image_manifest_order`, `result_evidence`, `summary`

Excluded: `artifact_created_at`, `integrity`, and other non-deterministic fields.

## 8. Provider order validation

Soft warnings recorded in `provider_image_manifest_order.warnings` for:

- Unknown `manifest_entry_id`
- `source_image_id` conflict with execution manifest
- `role` conflict with execution manifest
- Duplicate `provider_position`
- Duplicate `manifest_entry_id`

## 9. Summary classification

UNVALIDATED rows classified by warning text:

- `manifest_unavailable`, `manifest_invalid`, `unvalidated_unknown`

INVALID rows classified by warning text (not IMG_* heuristics):

- `unknown_identifier`, `conflicting_identifier`, `malformed_identifier`, `reference_rejected`

## 10. Failure behavior

| Failure | Behavior |
|---------|----------|
| Missing structural rows (required photo job) | `TRACEABILITY_EVIDENCE_MISSING` |
| Missing required manifest | `TRACEABILITY_MANIFEST_MISSING` |
| Corrupt required manifest | `TRACEABILITY_MANIFEST_INVALID` |
| Generation error | `ARTIFACT_SOURCE_STAGING_FAILED` with `artifact_kind=traceability_manifest` |
| Required traceability + no outbox | `ARTIFACT_OUTBOX_REQUIRED_FOR_TRACEABILITY` |
| Missing file at staging | `ARTIFACT_SOURCE_MISSING` |
| Staging/upload failure | Outbox retry / permanent fail; `failed_kinds` includes `traceability_manifest` |
| Non-photo / not canonical | Artifact not required |

Domain persistence remains committed per existing finalization semantics.

## 11. Tests

| Module | Tests |
|--------|-------|
| `test_traceability_manifest_builder_phase47.py` | 25 |
| `test_traceability_artifact_service_phase47.py` | 9 |
| `test_traceability_artifact_publication_phase47.py` | 4 |
| `test_traceability_artifact_finalization_phase47.py` | 5 |
| `test_artifact_manifest_store.py` | 7 |

**Phase 4.7 targeted suite:** 50 passed, 0 failed, 0 skipped

**Artifact manifest store suite:** 7 passed (included above)

**Phase 4.6 regression:** 28 passed, 0 failed, 0 skipped

**Phase 4.5 regression:** 79 passed, 0 failed, 0 skipped

**Artifact/Gemini regression:** 66 passed, 1 skipped, 0 failed

**Frontend regression:** 60 passed, 0 failed

**`compileall src`:** success

## 12. Files changed (corrections)

| Area | Files |
|------|-------|
| Domain | `traceability_artifact/builder.py`, `errors.py`, `jobs/artifact_policy.py` |
| Application | `traceability_artifact_service.py` |
| Infrastructure | `v3_job_executor.py`, `memory_artifact_manifest_store.py`, `sql_artifact_manifest_store.py` |
| Tests | phase47 modules, `test_artifact_manifest_store.py`, `test_worker_phase3_part5_artifact_outbox.py` |

## 13. Phase 4.7 code-review corrections

Applied after `CHANGES_REQUESTED`:

1. **Static + dynamic required artifact semantics** — shared helpers in `artifact_policy.py`; both memory and SQL stores delegate.
2. **Dynamic `missing_required_kinds`** — includes `traceability_manifest` when `required=True` and not published.
3. **Stable hash behavior** — `artifact_created_at` separated; `traceability_manifest_hash_excludes` documented in integrity block.
4. **Explicit V3 photo requirement** — `is_required_for_run(input_type, canonical_traceability_expected, ...)`; executor passes job context.
5. **Missing/corrupt manifest fail-closed** — `TraceabilityManifestMissingError`, `TraceabilityManifestInvalidError`.
6. **Non-outbox publication policy** — Option A: fail finalization when required traceability cannot use outbox.
7. **Provider order validation** — soft warnings for inconsistent metadata.
8. **Summary classification** — warning-based unavailable/invalid/unknown/conflict/malformed/reference counts.

## 14. Remaining risks

- Historical jobs lack `traceability_manifest.json` (no backfill)
- API/frontend still read JSON summaries (Phase 4.8)
- Photo V3 jobs without artifact outbox configured will fail at finalization (intentional fail-closed policy)

## 15. Phase 4.8 readiness

**Ready for planning.** Durable traceability artifacts are published and queryable offline. Phase 4.8 can expose structural evidence via API/frontend read models using the same schema fields.
