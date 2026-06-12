# Phase 3 — Robust Job Finalization (Read-Only Audit)

## 1. Executive summary

| Field | Value |
| ----- | ----- |
| **Verdict** | `READY_WITH_RISKS` |
| **Highest-risk finding** | Post-persistence finalization has **no durable stage markers** and **non-transactional** job/aisle transitions; a failure after domain commit leaves **committed results + FAILED job** with no machine-readable distinction between persist vs artifact vs `mark_success` failures (`v3_job_executor.py:786–797`, `v3_job_executor.py:540–639`). |
| **Phase 3 safe to begin?** | Yes, incrementally — but **must not** treat Phase 2 UoW as covering artifact upload or terminal job transition. |
| **Phase 2 guarantees sufficient?** | **Partially.** Phase 2 Part 2 guarantees **atomic delete-replace + job-scoped recompute** inside `PersistAisleResultUseCase` (`persist_aisle_result.py:110–143`). It does **not** cover artifacts, execution-log durability, `mark_success`, operational promotion, or inventory reconcile. |
| **Main blockers** | (1) No formal Phase 3 spec file in repo (scope taken from user audit brief + Phase 2 audit gaps). (2) SQL Part 2/Part 3 integration suites still `PENDING_SQL_SERVER_VALIDATION` per `audit/worker-phase-2-part-2-transactional-idempotency.md`. (3) No targeted recovery API for post-persist failures. |
| **Confidence** | **High** for finalization ordering and persist transaction boundary (code + memory tests). **Medium** for SQL production atomicity (tests skip without ODBC). **High** for partial-finalization characterization (WKR-P1 / Phase 5 tests). |

**P0 count:** 3  
**P1 count:** 5  
**Highest-risk partial-completion scenario:** Persistence + recompute committed, durable artifact upload fails → domain rows durable, job/aisle `FAILED`, `result_json` lacks `durable_artifacts` (Scenario C/D family; `test_wkr_p1_t002_artifact_failure_after_persist_leaves_domain_rows_failed_job`).  
**Targeted recovery currently exists?** **No** — only `CleanupJobResultsUseCase` (explicit delete) and full **new-job retry** (`retry_aisle_job.py`). No recompute-only, republish-only, or resume-finalization path.  
**Recommended first implementation part:** **Phase 3.2 — Finalization stage and error taxonomy** (minimal metadata + specific error codes before recovery UX).  
**Code modified during audit?** **No**

---

## 2. Scope and methodology

### Paths inspected

| Area | Paths |
| ---- | ----- |
| Worker entry | `backend/src/jobs/worker.py`, `backend/src/jobs/worker_bootstrap.py`, `backend/src/jobs/job_store.py` |
| Executor / finalization | `backend/src/infrastructure/pipeline/v3_job_executor.py`, `v3_job_execution_state.py`, `v3_execution_artifacts_service.py`, `worker_durable_artifact_publisher.py` |
| Domain persist | `backend/src/application/use_cases/pipeline/persist_aisle_result.py`, `cleanup_job_results.py`, `recompute_consolidated_counts.py` |
| Transactions | `backend/src/application/ports/job_result_unit_of_work.py`, `backend/src/infrastructure/persistence/sql_job_result_unit_of_work.py`, `sql_job_result_scope_store.py`, `memory_job_result_unit_of_work.py` |
| State / promotion | `operational_result_promotion_service.py`, `sql_operational_job_promotion_repository.py`, `inventory_status_reconciler.py` |
| Normalization (pre-finalization) | `backend/src/pipeline/stages/analysis_stage.py`, `backend/src/llm/normalization/entity_normalizer.py` |
| Execution logs | `backend/src/pipeline/execution_log.py` |
| Retry / cancel | `retry_aisle_job.py`, `cancel_aisle_job.py`, `aisle_job_launch_service.py` |
| Persistence | `sql_job_repository.py`, `sqlserver.py`, `domain/jobs/entities.py`, `domain/aisle/entities.py` |
| Prior audits | `audit/worker-phase-2-part-2-transactional-idempotency.md`, `audit/worker-phase-2-part-3-operational-promotion-concurrency.md` |

### Tests inspected

- `test_worker_operational_safety_phase1.py` (WKR-P1 partial finalization, cancellation, mark_success failures)
- `test_worker_phase2_part2_transactional_idempotency.py` (+ SQL variant)
- `test_worker_phase2_part3_operational_promotion_concurrency.py`
- `test_v3_job_executor_phase5.py` (artifact failure, partial finalization comment)
- `test_v3_job_execution_state.py`, `test_worker_durable_artifact_publisher.py`
- `test_retry_aisle_job.py`, `test_cancel_aisle_job.py`

### Excluded

- Legacy worker path after v3 dispatch returns false (`worker.py:248–348`)
- CV detection/tracking stages (only pipeline → report boundary)
- Frontend UI reconciliation
- Production SQL validation runs (environment unavailable in audit)

### Assumptions

- Worker uses SQL mode with `SqlJobRepository.claim_next_queued_job` in production (`job_store.py:179–216`).
- `HybridInventoryPipeline` exit 0 implies `hybrid_report.json` exists in `{output}/{job_id}/run/`.
- Phase 3 scope follows the user audit brief; **no dedicated `Phase 3 Robust Finalization` spec document** was found in the repository.

### Limitations

- SQL rollback/commit behavior under concurrent workers: **UNVERIFIED_RUNTIME_BEHAVIOR** (tests skip without isolated SQL Server).
- S3 `put_object` overwrite semantics in production S3 adapter: inferred from deterministic keys; not runtime-tested here.
- Whether `mark_success` partial job save leaves `result_json.durable_artifacts` on subsequent `fail_job`: **inferred** from `fail_job` not clearing `result_json` (`v3_job_execution_state.py:176–189`); needs SQL integration test.

---

## 3. Exact finalization call graph

From **normalized provider response** through terminal job state:

```text
HybridInventoryPipeline.process_video / stages
  └─ AnalysisStage.run
       └─ normalize_llm_response(parsed_json, provider)     [analysis_stage.py:143]
       └─ entity resolution → hybrid_report.json written      [run_dir, pre-executor]

V3JobExecutor._v3_run_job_body
  └─ _v3_hybrid_run_and_load_report
       └─ cancellation_checkpoint("Pipeline", "post_pipeline")
       └─ json.load(run_dir / "hybrid_report.json")
  └─ _v3_persist_durables_and_mark_success
       ├─ ExecutionLogWriter.info("Persist", "Persist started")
       ├─ cancellation_checkpoint("Persist", "pre_persist")
       ├─ PersistAisleResultUseCase.execute
       │    ├─ hybrid_mapper → MappedAisleResult
       │    └─ JobResultUnitOfWork __enter__
       │         ├─ scope_store.delete_scope(inventory_id, aisle_id, job_id)
       │         ├─ _insert_mapped (positions, products, evidence, raw_labels)
       │         ├─ _recompute_job_scoped → JobScopedRecomputeFactory.create(repos).execute
       │         └─ uow.commit()
       ├─ ExecutionLogWriter.info("Persist", "Persist completed")
       ├─ V3ExecutionArtifactsService.require_store()
       ├─ cancellation_checkpoint("Artifacts", "pre_upload")   [inside broad try — see §13]
       ├─ publish_worker_durable_artifacts → ArtifactStore.put_object (×2–3)
       └─ V3JobExecutionStateService.mark_success
            ├─ job_repo.save(SUCCEEDED, result_json + durable_artifacts)
            ├─ OperationalResultPromotionService.promote_for_success (production)
            ├─ aisle_repo.save(PROCESSED, operational_job_id)
            └─ InventoryStatusReconciler.reconcile(inventory_id)

Exception routing (_v3_run_job_body):
  PipelineCancellationRequestedError → cancel_job_and_aisle
  Exception → fail_job_and_aisle (includes mark_success failures)
```

**Caller chain:** `worker.run_job` → `_try_v3_process_aisle` → `V3JobExecutor.execute` → `_v3_run_job_body` → `_v3_persist_durables_and_mark_success`.

---

## 4. Finalization sequence table

| Order | Stage | Component | State mutation | Transaction | Can fail | Failure consequence |
| ----- | ----- | --------- | -------------- | ----------- | -------- | ------------------- |
| 0 | Provider + normalize | `AnalysisStage` / `normalize_llm_response` | Local `hybrid_report.json`, pipeline exec log append | None (filesystem) | Yes | Pipeline exit ≠ 0 → `fail_job_and_aisle`; no domain persist |
| 1 | Load report | `V3JobExecutor._v3_hybrid_run_and_load_report` | None | None | Yes | `fail_job_and_aisle` if missing report |
| 2 | Persist start log | `ExecutionLogWriter.info` | Local `execution_log.jsonl` | None | Rare | Best-effort append; does not fail job |
| 3 | Pre-persist cancel check | `raise_if_cancellation_requested` | Exec log cancel events | None | Cancel | `cancel_job_and_aisle`; no persist |
| 4 | Map report | `PersistAisleResultUseCase._map_hybrid` | None | Pre-UoW | Yes | Exception → `fail_job_and_aisle`; no DB rows |
| 5 | Delete prior job scope | `JobResultScopeStore.delete_scope` | DELETE rows for `job_id` | UoW (uncommitted) | Yes | UoW rollback |
| 6 | Insert domain rows | `_insert_mapped` | INSERT positions, products, evidence, raw_labels | UoW | Yes | UoW rollback |
| 7 | Job-scoped recompute | `_recompute_job_scoped` | REPLACE/INSERT normalized_labels, final_count_records | UoW | Yes | UoW rollback (Phase 2) |
| 8 | Persist commit | `uow.commit()` | Domain + aggregates durable | **Commit** | Yes | Rollback if before commit |
| 9 | Persist complete log | `ExecutionLogWriter.info` | Local log | None | Rare | Job continues |
| 10 | Artifact store check | `V3ExecutionArtifactsService.require_store` | None | None | Yes | `fail_job_and_aisle` after step 8 committed |
| 11 | Pre-upload cancel check | `cancellation_checkpoint` | Exec log | None | Cancel | **Misrouted** — caught as artifact failure (§13 F) |
| 12 | Durable artifacts | `publish_worker_durable_artifacts` | S3/local objects | **Independent per put_object** | Yes | Partial uploads possible; `fail_job_and_aisle` |
| 13 | Mark success — job | `mark_success` → `job_repo.save` | `inventory_jobs`: SUCCEEDED, `result_json`, timestamps | **Auto-commit per save** | Yes | Exception → outer `fail_job_and_aisle` |
| 14 | Operational promotion | `promote_for_success` | `aisles.operational_job_id` CAS | Auto-commit | No (soft reject) | Job already SUCCEEDED; promotion outcome logged |
| 15 | Mark success — aisle | `aisle.mark_processed` + save | `aisles`: PROCESSED | Auto-commit | Yes | Job may already be SUCCEEDED in DB |
| 16 | Inventory reconcile | `InventoryStatusReconciler.reconcile` | `inventories.status` | Auto-commit | Yes | Job/aisle may already be updated |

**Confirmed order:** `normalize (pipeline) → persist domain + recompute (single UoW) → durable artifacts → mark_success (+ aisle + inventory)`.  
**Not** separate executor step: recompute runs **inside** persist UoW, not after artifact upload.

---

## 5. Transaction and commit map

### Inside one SQL/memory UoW (`PersistAisleResultUseCase`)

- **Begin:** `with self._uow_factory(base_repos) as uow` (`persist_aisle_result.py:110`)
- **Operations:** delete_scope → inserts → job-scoped recompute
- **Commit:** explicit `uow.commit()` (`persist_aisle_result.py:128`)
- **Rollback:** `__exit__` rolls back on any exception if not committed (`sql_job_result_unit_of_work.py:90–95`)

### Independent commit boundaries (partial durability points)

| # | Point | Mechanism | Partial state if later step fails |
| - | ----- | --------- | --------------------------------- |
| P1 | After `uow.commit()` | SQL transaction commit | Domain rows + normalized/final counts for `job_id` durable |
| P2 | After each `ArtifactStore.put_object` | `SqlServerClient.cursor()`-style independent I/O | Earlier artifact objects may exist at deterministic keys |
| P3 | After `job_repo.save` in `mark_success` | Each `SqlJobRepository.save` uses own connection + commit (`sqlserver.py:46–53`) | Job row may show SUCCEEDED + `result_json` |
| P4 | After `aisle_repo.save` in `mark_success` | Same | Aisle PROCESSED while job later overwritten to FAILED (race window) |
| P5 | After `fail_job` / `fail_job_and_aisle` | Separate save | Terminal FAILED without clearing prior `result_json` fields |

**Persistence and recompute share one transaction.** Job state updates do **not** share a transaction with domain results.

**Commits before artifact publication:** Yes — domain UoW commits at P1 before any `put_object`.

**Repository independent commit:** Yes — all v3 job/aisle/inventory repos use `client.cursor()` autocommit pattern, not the job-result UoW connection.

**Nested UoW:** None across persist vs mark_success.

---

## 6. State mutation map

| Entity | When written | Success path | Failure after persist | Cancel during finalization |
| ------ | ------------ | ------------ | --------------------- | --------------------------- |
| **Job** | `mark_running`, pipeline observer, heartbeat, `fail_job`, `cancel_job`, `mark_success` | SUCCEEDED, `result_json` + `durable_artifacts`, stage `completed` | FAILED, `failure_code=PROCESSING_FAILED`, generic `error_message` | CANCELED + `failure_code=CANCELED` if cooperative cancel path; FAILED if cancel caught in artifact `except Exception` |
| **Aisle** | `mark_running`, `fail_job_and_aisle`, `cancel_job_and_aisle`, `mark_success` | PROCESSED, `operational_job_id` set (production), errors cleared | FAILED (unless stale non-operational suppression), `retryable=True` | FAILED + `error_code=CANCELED` (cooperative) or FAILED (artifact-stage misroute) |
| **Inventory** | `InventoryStatusReconciler.reconcile` | Derived from aisle aggregate | Reconcile on fail path | Reconcile on cancel/fail |
| **Results** | Persist UoW | Job-scoped replace; tied to `job_id`, `aisle_id`, `inventory_id` | **Retained** on artifact/mark_success failure | Retained if persist completed before cancel at artifact stage |
| **Aggregates** | Inside persist UoW recompute | `normalized_labels`, `final_count_records` for `job_id` | Rolled back if recompute fails **before** commit; durable if commit succeeded | Same as results |
| **Artifacts** | `publish_worker_durable_artifacts` | 2–3 objects under `jobs/{job_id}/run/` | Partial objects possible; metadata not in `result_json` | None uploaded if fail before/during upload |
| **Logs** | `ExecutionLogWriter` (local throughout); uploaded as durable artifact | Local + durable NDJSON | Local persist stage logged; durable upload may fail | Cancel events in local log when checkpoint runs |

### Result association

- All inserted rows carry `job_id` from `PersistAisleResultCommand` (`persist_aisle_result.py:89–94`).
- `inventory_id` resolved from aisle (`persist_aisle_result.py:145–149`).
- Replacement: **delete-and-replace by `(inventory_id, aisle_id, job_id)`** before insert (`persist_aisle_result.py:113–117`, `sql_job_result_scope_store.py:107–139`).

---

## 7. Artifact catalog and criticality

| Artifact | Producer | Storage | Required for success | Idempotent | Reconstructable | Current failure behavior | Recommended criticality |
| -------- | -------- | ------- | -------------------- | ---------- | --------------- | ------------------------ | ------------------------ |
| `execution_log.jsonl` | Pipeline + executor (`ExecutionLogWriter`); uploaded by `publish_worker_durable_artifacts` | ArtifactStore (`jobs/{job_id}/run/execution_log.jsonl`) | **De facto yes** — upload required (`required=True`) | Overwrite same key on retry upload | Yes — from local `run_dir` if retained | Missing file → exception before upload; upload fail → job FAILED | **Critical** |
| `hybrid_report.json` | Pipeline reporting stage | Same prefix | **Yes** (`required=True`) | Overwrite | Yes — local file + can rebuild from domain with loss | Upload fail → FAILED; domain may exist | **Critical** |
| `hybrid_report.csv` | Pipeline | Same prefix | **No** (`required=False`) | Overwrite | Yes — local | Skipped if missing; upload fail on later required file still fails job | **Recoverable** |
| Local-only run artifacts (`input_manifest.json`, frames, etc.) | Pipeline | Filesystem under `run_dir` | No | N/A | Partial | Not uploaded; no job failure | **Best-effort** |
| `worker-launch.log` | `worker_bootstrap.append_worker_bootstrap_event` | `{output_dir}/{job_id}/worker-launch.log` | No | Append-only | Partial | Bootstrap fail → `WORKER_BOOTSTRAP_FAILED` | **Best-effort** |

**Classification in code:** Implicit only — executor comments document partial finalization after persist (`v3_job_executor.py:786–797`) but no enum/criticality field.

**Sensitive data:** Execution log sanitizes payloads (`execution_log.py:23–57`); `prompt_text` is **not** truncated. No raw images in durable set. Hybrid report may contain SKU/quantity supplier data.

---

## 8. Error taxonomy analysis

### Current `failure_code` values (job row)

| Code | Source | Collapsed scenarios |
| ---- | ------ | ------------------- |
| `PROCESSING_FAILED` | `fail_job` / `fail_job_and_aisle` (`v3_job_execution_state.py:184`) | Persist failure, artifact failure, mark_success failure, generic pipeline exception, inventory reconcile failure, **misclassified cancellation during artifact stage** |
| `CANCELED` | `cancel_job` (`v3_job_execution_state.py:198`) | Cooperative cancel on correct path |
| `WORKER_LAUNCH_FAILED` | `AisleJobLaunchService` | Spawn only |
| `WORKER_BOOTSTRAP_FAILED` | `worker_bootstrap.fail_v3_job_bootstrap` | Executor construction / top-level worker catch |
| `STALE_JOB` | `JobStaleReconciler` | Heartbeat timeout |

### Aisle `error_code`

- `PROCESSING_FAILED`, `CANCELED` via `mark_failed` — same collapse as job messages in `error_message` (truncated 2048).

### Generic error messages (not codes)

- Persist: `"Persist: {exc}"` (`v3_job_executor.py:565`)
- Artifacts: `"Durable artifact upload failed: {exc}"` (`v3_job_executor.py:618–621`)
- Pipeline: various strings via `fail_job_and_aisle`

**Gap:** System **cannot** reliably answer failure-mode questions 1–8 from codes alone; only message substring heuristics.

---

## 9. Partial completion evidence matrix

| Stage | Existing completion evidence | Reliable | Transactional | Recovery-safe | Gap |
| ----- | ---------------------------- | -------- | ------------- | ------------- | --- |
| Provider execution complete | Pipeline exit 0; `hybrid_report.json` exists | Medium | No | No | No DB marker; local file only |
| Normalization complete | Entities in report; `extraction_contract_version` in JSON | Medium | No | No | Not persisted separately |
| Results fully persisted | Rows for `job_id` in DB | **High** after commit | Yes (UoW) | Ambiguous on FAILED job | No `persist_completed_at` flag |
| Recompute complete | Same UoW commit as persist | **High** | Yes | Same | Not separable from persist |
| Artifacts published | `job.result_json.durable_artifacts` | **High when SUCCEEDED** | No | **No on FAILED** | Failed jobs explicitly lack metadata |
| Job transition complete | `job.status=SUCCEEDED`, `finished_at` | High when true | No | Retry creates **new** job id | FAILED may follow partial SUCCEEDED write |
| Finalization stage | `current_stage` / `current_substep` | **Low** | No | No | Not updated per finalization substep |
| Cancellation | `cancel_requested_at`, status `CANCEL_REQUESTED` | Medium | No | Partial | Finalization cancel conflated with FAIL |

### Can the system answer the audit questions?

| Question | Answer today |
| -------- | ------------- |
| Did provider execution complete? | **Partially** — exit 0 + report file; not durable in DB |
| Did normalization complete? | **Infer** from report schema only |
| Were results fully persisted? | **Infer** from row counts for `job_id`; no completion marker |
| Did recomputation complete? | **Same as persist** (same transaction) |
| Were required artifacts published? | **Only if SUCCEEDED** and `durable_artifacts` present |
| Was final job transition completed? | **`status=SUCCEEDED`** only; FAILED does not encode how far finalization got |

---

## 10. Retry and recovery matrix

| Failure point | Current retry behavior | Repeats provider | Repeats persistence | Duplicate risk | Targeted recovery exists | Safe |
| ------------- | ---------------------- | ---------------- | ------------------- | -------------- | ------------------------ | ---- |
| Pre-persist | `RetryAisleJobUseCase` → new job | Yes | No (new `job_id`) | Low cross-job | No | Yes with new job |
| Persist UoW failure | Same | Yes (new job) | Retries on same job id **not supported** (terminal FAILED) | N/A | No | Yes |
| Post-commit artifact failure | Retry new job | **Yes — full pipeline** | Old rows remain for failed `job_id` | Artifact key overwrite on **same** job id if manually re-run | No | **Risky** — duplicate provider cost; orphan domain on failed job |
| mark_success failure | Outer fail → FAILED | Manual retry new job | Domain exists for failed job | Job row ambiguity | No | **Risky** |
| Cancel mid-finalization | Terminal CANCELED or FAILED | New job after retry | Depends if persist ran | Domain rows if persist completed | No | Cleanup UC optional |
| Stale job | `reclaim_stale_running_jobs` → FAILED | Relaunch | — | — | No | Partial |

**Targeted recovery operations:** **None implemented.**  
`CleanupJobResultsUseCase` deletes job-scoped rows but does not republish artifacts or reconcile status (`cleanup_job_results.py`).

---

## 11. Scenario reconstruction (mandatory A–H)

### Scenario A — Provider OK, normalization OK, persistence fails before commit

| Dimension | Result |
| --------- | ------ |
| Job state | `FAILED`, `failure_code=PROCESSING_FAILED`, `error_message` starts with `Persist:` |
| Aisle | `FAILED`, `error_code=PROCESSING_FAILED` |
| Inventory | Reconciled (typically FAILED if all aisles fail) |
| Domain results | **None** for job (UoW rollback) — `test_wkr_p1_t001` |
| Aggregates | Empty for job scope |
| Artifacts | Not uploaded |
| Execution log | Local entries for Persist start/fail |
| Retry safety | New job safe |
| Operator visibility | Failed aisle; no operational slice |

### Scenario B — Some rows written, persistence fails

| Dimension | Result |
| --------- | ------ |
| **Phase 2 behavior** | **Full rollback** — no partial rows (`test_wkr_p1_t001`, Part 2 audit) |
| Job / aisle | Same as A |
| Domain | **Zero rows** after failure (not partial) |
| Note | Pre-Part-2 comment in WKR-P1-T007 docstring is **stale**; test asserts 0 positions |

### Scenario C — Persistence commits, recompute fails

| Dimension | Result |
| --------- | ------ |
| **Inside same UoW** | Recompute failure **rolls back entire persist** including inserts (`test_wkr_p1_t007`, `test_worker_phase2_part2_transactional_idempotency.py`) |
| Job | FAILED |
| Domain | No rows |
| **Interpretation** | "Persistence succeeds, recompute fails" **after commit** cannot occur today — recompute is pre-commit |

### Scenario D — Persist OK, recompute OK, first artifacts OK, later artifact fails

| Dimension | Result |
| --------- | ------ |
| Job | FAILED, no `durable_artifacts` in `result_json` |
| Domain | Committed |
| Artifacts | **Partial** — earlier `put_object` calls may have succeeded (`publish_worker_durables` sequential loop); **UNVERIFIED_RUNTIME_BEHAVIOR** for which objects remain without dedicated test |
| Aisle | FAILED |
| Retry (new job) | Full pipeline; old domain rows remain under failed `job_id` |
| Test coverage | **Not covered** for mid-sequence artifact fail (`fail_on_call=2` exists in doubles but no finalization test) |

### Scenario E — Persist OK, artifacts OK, mark_success fails

| Dimension | Result |
| --------- | ------ |
| Job | FAILED via outer `except Exception` → `fail_job_and_aisle` (`test_wkr_p1_t003_case_a`) |
| Artifacts | Uploaded (`ArtifactUploadSpy` ≥2 keys) |
| Domain | Committed |
| `result_json` | **No durable_artifacts** if job save failed before merge; **UNVERIFIED** if job save succeeded then aisle failed |
| Aisle | FAILED |
| mark_success idempotent retry | **Not safe** — same job id stays FAILED; no resume API |

### Scenario F — Persist OK, cancellation before artifact publication

| Dimension | Result |
| --------- | ------ |
| Domain | Committed (2 positions in `test_wkr_p1_t006b`) |
| Job | **`FAILED`**, not `CANCELED` (`test_wkr_p1_t006b`) |
| Root cause | `PipelineCancellationRequestedError` raised at `pre_upload` is caught by `except Exception as artifact_exc` (`v3_job_executor.py:582–623`) |
| Artifacts | Not uploaded |
| Aisle | FAILED (not canceled mapping) |
| Retry | New job; optional `CleanupJobResultsUseCase` |

### Scenario G — Retry after persist OK, artifacts failed

| Dimension | Result |
| --------- | ------ |
| Mechanism | `RetryAisleJobUseCase` creates **new** `job_id`, reruns **full** pipeline (`retry_aisle_job.py:110–118`) |
| Old job | FAILED, domain rows retained (non-operational) |
| New job | New job-scoped rows after success |
| Artifacts | New keys under new `job_id` |
| Duplicate provider | **Yes** |
| Targeted republish | **Does not exist** |

### Scenario H — Two workers finalizing same job

| Dimension | Result |
| --------- | ------ |
| Claim | `claim_next_queued_job` uses `UPDLOCK, READPAST, ROWLOCK` — one worker claims QUEUED→STARTING (`sql_job_repository.py:384–394`) |
| Same job twice | Executor skips non-`STARTING` (`v3_job_executor.py:296–300`) except cancel paths |
| Concurrent persist same `job_id` | **No lock** — Phase 2 audit gap; **UNVERIFIED_RUNTIME_BEHAVIOR** on SQL |
| mark_success race | No CAS on job terminal transition |
| Safeguard | Queue claim only; **missing finalization lease** |

---

## 12. Concurrency analysis

| Risk | Safeguard | Gap |
| ---- | --------- | --- |
| Double claim from queue | SQL atomic UPDATE…OUTPUT | OK for QUEUED |
| Same job two workers | Status gate STARTING only | Stale reclaim + relaunch edge cases |
| Concurrent persist same job | None | P2 Part 2 audit deferred |
| Artifact double publish | Deterministic keys → overwrite | Orphan content if partial |
| mark_success vs mark_failed race | Last write wins per repo | No versioning |
| Cancel vs success | Cooperative poll of `CANCEL_REQUESTED` | Artifact-stage cancel → FAIL path |
| Result replace vs another job | Job-scoped delete | OK across jobs |

---

## 13. Test coverage matrix

| Scenario | Test file | Coverage | Critical assertion | Missing coverage |
| -------- | --------- | -------- | ------------------ | ---------------- |
| Persist success | `test_worker_phase2_part2_transactional_idempotency.py` | Fully covered (memory) | Idempotent replace | SQL runtime |
| Persist partial failure | `test_wkr_p1_t001` | Fully covered | 0 rows after fail | — |
| Transaction rollback | Part 2 T004–T006, SQL T010–T012 | Partial | Memory proven | SQL pending |
| Recompute failure | `test_wkr_p1_t007`, Part 2 | Fully covered | Rollback includes recompute | — |
| Artifact failure after persist | `test_wkr_p1_t002`, `test_v3_job_executor_phase5.py` | Fully covered | Domain retained, job FAILED | — |
| Partial artifact publication | — | **Not covered** | — | Mid-upload fail |
| mark_success job save fail | `test_wkr_p1_t003_case_a` | Fully covered | Artifacts exist, job FAILED | SQL |
| mark_success aisle save fail | `test_wkr_p1_t003_case_b` | Partially covered | Aisle not PROCESSED | `result_json` ambiguity |
| fail_handler failure | — | **Not covered** | — | fail_job throws |
| Cancel during finalization | `test_wkr_p1_t006b` | **Test exists, wrong invariant** | Documents FAIL not CANCEL | Fix or assert misroute |
| Retry after persist | `test_wkr_p1_t012`, `test_retry_aisle_job.py` | Partial | New job isolation | No republish-only |
| Concurrent finalization | Part 3 promotion tests | Partial | Promotion CAS | Same-job double persist |
| Idempotent artifact upload | `test_worker_durable_artifact_publisher.py` | Partial | Key determinism | End-to-end retry upload |
| Final state reconciliation | — | **Not covered** | — | Operator reconcile job |

---

## 14. Findings

### P0 — Critical

#### F-P0-1: No durable finalization stage metadata
- **Evidence:** Job entity has no `finalization_stage` / persist timestamp (`domain/jobs/entities.py`); executor only logs structurally (`v3_job_executor.py:568–572`).
- **Affected files:** `v3_job_executor.py`, `domain/jobs/entities.py`, `inventory_jobs` schema
- **Current behavior:** FAILED jobs indistinguishable by stage except message substring.
- **Failure scenario:** Artifact fail after persist vs mark_success fail.
- **Impact:** Cannot implement safe targeted recovery or operator truth table.
- **Likelihood:** High (known partial path documented in code).
- **Detectability:** Low without DB inspection + object store inspection.
- **Recommendation:** Phase 3.2 — persist stage enum + timestamps on job row.
- **Required tests:** Failure at each stage asserts metadata.
- **Blocks implementation:** **Yes** for recovery (not for taxonomy-only work).

#### F-P0-2: Cancellation during artifact upload classified as PROCESSING_FAILED
- **Evidence:** `cancellation_checkpoint` inside `except Exception` artifact handler (`v3_job_executor.py:582–623`); `PipelineCancellationRequestedError` subclasses `RuntimeError` (`errors.py:4–8`); `test_wkr_p1_t006b` expects FAILED.
- **Impact:** Wrong terminal state; domain rows retained; operator sees processing failure not cancel.
- **Likelihood:** Medium (cancel during upload window).
- **Detectability:** Medium (log may show cancel events + FAIL message).
- **Recommendation:** Re-raise `PipelineCancellationRequestedError` before artifact `except Exception`; or narrow catch.
- **Required tests:** Assert CANCELED + domain cleanup policy.
- **Blocks implementation:** No, but should fix early in Phase 3.

#### F-P0-3: mark_success is multi-transaction without compensation
- **Evidence:** `job_repo.save` then `aisle_repo.save` then reconcile — separate autocommits (`v3_job_execution_state.py:140–174`, `sqlserver.py:46–53`).
- **Impact:** SUCCEEDED job row possible momentarily; artifacts uploaded but aisle FAILED; `fail_job` may not clear `result_json`.
- **Likelihood:** Low per-request, non-zero at scale.
- **Detectability:** Low.
- **Recommendation:** Phase 3.3 — single terminal transaction or outbox + reconcile worker.
- **Required tests:** Case B + SQL integration for `result_json` after fail.
- **Blocks implementation:** No for metadata-first approach.

### P1 — High

#### F-P1-1: Generic PROCESSING_FAILED collapses finalization failures
- **Evidence:** `fail_job` always sets `PROCESSING_FAILED` (`v3_job_execution_state.py:184`).
- **Recommendation:** Phase 3.2 error codes: `PERSIST_FAILED`, `ARTIFACT_PUBLISH_FAILED`, `MARK_SUCCESS_FAILED`, etc.

#### F-P1-2: Partial artifact upload without rollback
- **Evidence:** Sequential `put_object` in loop (`worker_durable_artifact_publisher.py:114–162`).
- **Recommendation:** Phase 3.5 artifact outbox or two-phase publish + metadata only after all required uploads.

#### F-P1-3: No targeted recovery — full job retry only
- **Evidence:** `RetryAisleJobUseCase` always launches new job + pipeline (`retry_aisle_job.py`).
- **Recommendation:** Phase 3.4 manual ops: `republish_artifacts`, `reconcile_job_status`.

#### F-P1-4: Execution log durability coupled to end-of-run upload
- **Evidence:** Local log throughout; durable copy only in step 12.
- **Impact:** Persist-stage failures have local logs only until upload succeeds.
- **Recommendation:** Classify local log as recoverable; optional early upload not required for success.

#### F-P1-5: SQL validation gap for production approval
- **Evidence:** `audit/worker-phase-2-part-2-transactional-idempotency.md` — SQL tests pending.
- **Recommendation:** Run P2-P2-T010–T012, P2-P3-T014–T016 before prod deploy; blockers for **deployment**, not Phase 3 design start.

### P2 — Medium

#### F-P2-1: `current_stage` not updated during Persist/Artifacts substeps
- **Evidence:** `update_runtime_status` only from pipeline observer (`v3_job_executor.py:743–750`).

#### F-P2-2: Retry leaves failed job domain rows until explicit cleanup
- **Evidence:** Phase 2 failed-result retention policy (`audit/worker-phase-2-part-3-operational-promotion-concurrency.md`).

#### F-P2-3: No unique constraints on business keys (Phase 2 deferred)
- **Evidence:** Part 2 audit §10.

### P3 — Low

#### F-P3-1: WKR-P1-T007 docstring contradicts Phase 2 rollback behavior
- **Evidence:** Comment says "entity rows persist"; test asserts 0 rows.

---

## 15. Proposed Phase 3 model (recommendations — not implemented)

### Facts (current code)
- Finalization order: persist (incl. recompute) → artifacts → mark_success.
- Persist is transactional; later steps are not.
- FAILED after persist leaves domain data; no auto compensation.
- Retry = new job id + full pipeline.

### Finalization stages (proposed minimum)
1. `DOMAIN_PERSISTED` (UoW commit OK)
2. `ARTIFACTS_PUBLISHED` (all required puts OK)
3. `JOB_SUCCEEDED` (job row terminal)
4. `AISLE_RECONCILED` (aisle + inventory)

### Specific error codes (proposed)
- `PERSIST_FAILED`, `RECOMPUTE_FAILED` (if ever split), `ARTIFACT_PUBLISH_FAILED`, `ARTIFACT_STORE_UNAVAILABLE`, `MARK_SUCCESS_FAILED`, `AISLE_PROMOTION_FAILED`, `INVENTORY_RECONCILE_FAILED`, `FINALIZATION_CANCELED`

### Partial completion metadata (proposed fields on `inventory_jobs`)
- `finalization_stage`, `domain_persisted_at`, `artifacts_published_at`, `finalization_error_code`, `finalization_error_detail` (JSON, bounded)

### Recovery eligibility
- `DOMAIN_PERSISTED` + artifact fail → eligible for **republish only**
- `ARTIFACTS_PUBLISHED` + mark fail → **reconcile status only**
- Never auto full pipeline retry as default for post-persist failures

### Idempotent recovery operations (proposed)
- `RepublishWorkerArtifacts(job_id)` — reuse local run_dir or reconstruct report from domain
- `ReconcileJobTerminalState(job_id)` — idempotent mark_success if invariants pass
- `CleanupJobResults` — already exists

### Success invariants (proposed)
- Job SUCCEEDED iff `finalization_stage=COMPLETE` AND required artifacts in `result_json` AND (production) promotion outcome acceptable.

---

## 16. Recommended implementation breakdown

### Phase 3.2 — Finalization stage and error taxonomy
- **Objective:** Distinguish failure modes 1–8 without large executor refactor.
- **Scope:** Executor catch blocks + `fail_job` variants; job columns or `result_json` finalization block.
- **Dependencies:** None.
- **Risks:** Migration for new columns.
- **Required tests:** Scenarios A, D, E, F with code assertions.
- **Exit criteria:** Each failure point sets distinct `failure_code` + stage.

### Phase 3.3 — Durable partial-completion metadata
- **Objective:** Operators and recovery logic read stage timestamps from DB.
- **Scope:** Write markers at P1, P2, P3 commit points.
- **Dependencies:** 3.2 taxonomy.
- **Risks:** Stale markers if write fails mid-flight.
- **Required tests:** Metadata present after partial failures.
- **Exit criteria:** API exposes finalization progress for FAILED jobs.

### Phase 3.4 — Manual targeted recovery
- **Objective:** Admin/use-case endpoints for republish + reconcile.
- **Scope:** Application layer only; no automatic full retry.
- **Dependencies:** 3.2, 3.3.
- **Risks:** Invoking reconcile without artifact invariants.
- **Required tests:** Scenario G with republish-only path.
- **Exit criteria:** Operator can complete finalization without re-running LLM.

### Phase 3.5 — Artifact retry or outbox
- **Objective:** Atomic required-artifact set or compensating delete on partial upload.
- **Scope:** `publish_worker_durable_artifacts` + store adapter.
- **Dependencies:** 3.3 metadata.
- **Risks:** S3 partial delete.
- **Required tests:** Scenario D mid-fail.
- **Exit criteria:** No orphaned required artifacts without metadata.

### Phase 3.6 — Operator visibility and reconciliation
- **Objective:** UI/API surfaces partial completion + recommended action.
- **Scope:** Frontend + v3 status DTOs.
- **Dependencies:** 3.2–3.4.
- **Exit criteria:** Runbook actions map 1:1 to recovery ops.

---

## 17. Final readiness verdict

| Question | Answer |
| -------- | ------ |
| **Should implementation begin?** | **Yes**, starting with **Phase 3.2** (taxonomy + cancel fix in artifact handler). |
| **First part** | Phase 3.2 — finalization stage and error taxonomy (+ narrow exception handling for cancel). |
| **Blockers to resolve** | (1) Run SQL integration suites when DB available. (2) Add/adopt written Phase 3 spec aligned with this audit. (3) Decide cancel-after-persist policy: retain vs cleanup domain rows. |
| **Invariants that must not be violated** | Phase 2 job-scoped UoW atomicity; operational read isolation (`operational_job_id`); never mark SUCCEEDED without required durable artifacts in `result_json`; do not default to full pipeline retry for post-persist failures. |

**Final recommendation:** `READY_WITH_RISKS`

---

*Audit performed read-only. No production code, migrations, tests, or configuration were modified.*
