# Phase 4.6 — Structural Evidence Persistence

## 1. Executive summary

**Verdict:** COMPLETE

| Item | Status |
|------|--------|
| Structural `result_evidence` persistence | Yes |
| VALID / INVALID / MISSING / UNVALIDATED rows persisted | Yes |
| Transactional with `PersistAisleResultUseCase` | Yes |
| Delete-replace per `job_id` on retry | Yes |
| `source_asset_id` linked via manifest when available | Yes |
| Fail-closed `has_valid_evidence` | Yes |
| JSON/report/API backward compatible | Yes |
| Artifact/Gemini regressions | Yes (66 passed, 1 skipped) |
| Video traceability | No |
| Phase 4.7 started | No |

## 2. Data model

**Table:** `result_evidence` (distinct from crop/media `evidences` table)

| Field | Purpose |
|-------|---------|
| `id` | Primary key |
| `job_id`, `inventory_id`, `aisle_id` | Execution scope |
| `position_id` | Link to persisted position when available |
| `entity_uid`, `model_entity_id` | Entity identity |
| `raw_manifest_entry_id`, `manifest_entry_id` | Provider audit |
| `raw_source_image_id` | Legacy provider ID audit |
| `resolved_manifest_entry_id` | Manifest resolution audit |
| `source_image_id` | Stable primary evidence ID (VALID only) |
| `source_asset_id` | Canonical asset linkage |
| `traceability_status`, `traceability_warning` | Outcome |
| `role` | `primary_evidence` / `reference_image` / `unknown` |
| `provider`, `model_name`, `schema_version`, `manifest_version` | Context |
| `has_valid_evidence` | Fail-closed display flag |
| `evidence_kind` | `entity_traceability` |
| `created_at`, `updated_at` | Timestamps |

**Migration:** `backend/src/database/migrations/versions/0042_result_evidence_structural_persistence.sql`

**Indexes:** `job_id`, `job_id+entity_uid`, `job_id+model_entity_id`, `job_id+traceability_status`, `job_id+source_image_id`, `job_id+source_asset_id`, `job_id+resolved_manifest_entry_id`

## 3. Persistence flow

```text
hybrid_report entity dict
  → map_entity_to_result_evidence() (domain/result_evidence/mapper.py)
  → MappedAisleResult.result_evidence_records
  → PersistAisleResultUseCase._insert_mapped()
  → ResultEvidenceRepository.save_many()
  → same UoW transaction as positions/products/crop evidences
```

Provider/model/prompt composition passed via `PersistAisleResultCommand` from `V3JobExecutor`.

## 4. Evidence status matrix

| Input | Status | `source_image_id` | `source_asset_id` | Displayable |
|-------|--------|-------------------|-------------------|-------------|
| VALID primary IMG_001 | VALID | asset-1 | asset-1 | Yes |
| REF_001 | INVALID | null | ref-1 (audit) | No |
| IMG_999 | INVALID | null | null | No |
| Missing evidence | MISSING | null | null | No |
| Manifest unavailable | UNVALIDATED | null | null | No |
| Conflicting IDs | INVALID | null | null | No |

Displayable only when: `traceability_status=valid` AND `has_valid_evidence=true` AND `role=primary_evidence` AND manifest confirms primary entry (when manifest present).

## 5. Retry/idempotency

Scope: **`job_id`** (same as existing result persistence).

On each persist: `scope_store.delete_scope()` removes prior `result_evidence` rows for `job_id` before insert. Retry replaces rows; no append duplication.

## 6. Transactional behavior

`result_evidence` participates in `JobResultRepositories` bundle and memory/SQL UoW snapshots. Failure during position/product insert rolls back evidence rows; `save_many` runs after position loop in same transaction.

## 7. Backward compatibility

- `hybrid_report.json`, `detected_summary_json`, API responses unchanged
- Crop `evidences` table unchanged
- No frontend changes
- Old jobs without `result_evidence` rows continue using JSON fields

## 8. Tests

| Module | Tests |
|--------|-------|
| `test_structural_evidence_mapping_phase46.py` | 6 |
| `test_evidence_repository_phase46.py` | 1 |
| `test_result_evidence_persistence_phase46.py` | 3 |
| `test_structural_evidence_persistence_phase46.py` | 1 |
| `test_migration_0042_result_evidence.py` | 1 |

**Phase 4.6 targeted suite:** 67 passed, 0 failed, 0 skipped

**Artifact/Gemini regression:** 66 passed, 1 skipped, 0 failed

**Frontend regression:** 60 passed, 0 failed

**`compileall src`:** success

## 9. Files changed

| Area | Files |
|------|-------|
| Domain | `result_evidence/entities.py`, `result_evidence/mapper.py` |
| Application | `persist_aisle_result.py`, `mapped_aisle_result.py`, ports |
| Infrastructure | SQL/memory repos, scope stores, UoW, `v3_report_mapper.py`, `v3_job_executor.py` |
| Runtime | `repository_builders.py`, `app_container.py`, `v3_deps.py`, `worker.py` |
| Database | migration 0042, `schema.sql` |
| Tests | 5 new modules + harness/persist deps updates |

## 10. Remaining risks

- Historical backfill for pre-4.6 jobs not implemented (JSON-only legacy)
- Durable manifest artifact (Phase 4.7) not implemented
- API/frontend structural evidence read model (Phase 4.8) not implemented
- Crop-level evidence persistence unchanged (separate `evidences` table)

## 11. Phase 4.7 readiness

**Ready for planning.** Phase 4.6 provides queryable structural traceability rows per job/entity. Phase 4.7 can publish durable manifest/traceability artifacts knowing structural evidence is persisted transactionally with domain results.
