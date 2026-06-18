# Phase 4.7 — Durable Traceability Artifact

## 1. Executive summary

**Verdict:** COMPLETE

| Item | Status |
|------|--------|
| Durable `traceability_manifest.json` implemented | Yes |
| Generated from structural `result_evidence` rows | Yes |
| Includes execution image manifest + provider order | Yes |
| Fail-closed `displayable` in artifact | Yes |
| Published via existing artifact outbox | Yes |
| Required for V3 photo jobs (canonical manifest present) | Yes |
| Deterministic hashes + JSON-safe content | Yes |
| Idempotent outbox registration per job/kind | Yes |
| Phase 4.6 / 4.5 / artifact regressions | Yes |
| Video traceability | No |
| Phase 4.8 started | No |

## 2. Artifact schema

**File:** `traceability_manifest.json`  
**Schema version:** `phase-4.7.traceability_manifest.v1`

| Section | Purpose |
|---------|---------|
| `execution_image_manifest` | Canonical Phase 4.3 manifest projection |
| `provider_image_manifest_order` | Provider payload order or deterministic unavailable warning |
| `result_evidence` | Structural rows from Phase 4.6 with `displayable` flag |
| `summary` | Counts by traceability status and displayability |
| `integrity` | SHA-256 hashes (`execution_image_manifest_hash`, `result_evidence_hash`, `traceability_manifest_hash`) |

## 3. Source of truth

Priority:

1. Structural `result_evidence` rows (`list_for_scope`)
2. Canonical `execution_image_manifest` from prompt composition
3. `provider_image_manifest_order` from run metadata
4. `hybrid_report` — not used when structural rows exist (parameter accepted but ignored)

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

## 5. Failure behavior

| Failure | Behavior |
|---------|----------|
| Missing structural rows (photo job) | `TRACEABILITY_EVIDENCE_MISSING`; finalization fails at generation |
| Generation error | `ARTIFACT_SOURCE_STAGING_FAILED` with `artifact_kind=traceability_manifest` |
| Missing file at staging | `ARTIFACT_SOURCE_MISSING` |
| Staging/upload failure | Outbox retry / permanent fail; `failed_kinds` includes `traceability_manifest` |
| Non-photo / no manifest | Artifact not generated or required |

Domain persistence remains committed per existing finalization semantics.

## 6. Idempotency

- Content hash stable for identical structural rows + manifest + provider order
- Outbox unique on `(job_id, artifact_kind)` — re-register updates same entry
- `required_kinds_published` uses per-entry `required` flag (supports photo-only traceability requirement)

## 7. JSON safety

Built only from domain strings/numbers/bools/lists/dicts. No image bytes, SDK objects, prompts, or signed URLs. `traceability_manifest_is_json_safe()` guards before write.

## 8. Tests

| Module | Tests |
|--------|-------|
| `test_traceability_manifest_builder_phase47.py` | 8 |
| `test_traceability_artifact_service_phase47.py` | 3 |
| `test_traceability_artifact_publication_phase47.py` | 3 |
| `test_traceability_artifact_finalization_phase47.py` | 3 |

**Phase 4.7 targeted suite:** 17 passed, 0 failed, 0 skipped

**Phase 4.6 regression:** 20 passed, 0 failed, 0 skipped

**Phase 4.5 + artifact/Gemini regression:** 162 passed, 1 skipped, 0 failed

**Frontend regression:** 60 passed, 0 failed

**`compileall src`:** success

## 9. Files changed

| Area | Files |
|------|-------|
| Domain | `traceability_artifact/builder.py`, `canonical_json.py`, `errors.py` |
| Application | `traceability_artifact_service.py`, `artifact_publication_dispatcher.py`, `artifact_publication_source_policy.py` |
| Policy | `artifact_policy.py` |
| Infrastructure | `v3_job_executor.py`, `worker_durable_artifact_publisher.py`, manifest stores, result evidence repos |
| Tests | 4 new phase47 modules + doubles fix |

## 10. Remaining risks

- Historical jobs lack `traceability_manifest.json` (no backfill)
- API/frontend still read JSON summaries (Phase 4.8)
- Legacy non-outbox durable upload path does not publish traceability unless dispatcher configured

## 11. Phase 4.8 readiness

**Ready for planning.** Durable traceability artifacts are published and queryable offline. Phase 4.8 can expose structural evidence via API/frontend read models using the same schema fields.
