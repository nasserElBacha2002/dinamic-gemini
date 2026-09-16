# Phase 2 corrections — validation

## Changes performed

1. **CAS lease requeue** — `ExportPrepRepository.requeueExpiredLease` / `enqueueIdempotent` only reclaim expired in-flight leases via UPDATE conditioned on `capture_photo_id` + observed `status` + observed `lease_token` + expiry/`NULL` token; `changes !== 1` → reread, `requeued: false`. `renewLease` may extend an already-expired lease **only** when `lease_token` still matches (documented vs CAS).
2. **Central READY validation** — `validateReadyStaging(job, mode)` (`light` = metadata + file + real size; `strong` = + SHA recompute). Used in backfill, export preflight, reinclude/promote, recovery paths. `promoteQueuedToReadyIfComplete` requires a validate callback (not SQL metadata alone).
3. **Missing sources** — FINISH / REVIEW_OPEN / EXPORT_PREFLIGHT increment `missingSourcePhotos` + structured `partialErrors` when URI unreadable; no silent success.
4. **onPhotoStable / finish** — CaptureService **awaits** the returned Promise inside `activeValidations`; finish waits for those validations. Comment corrected: enqueue barrier only — **not** Phase 3 prep drain. Deferred-Promise test added.
5. **Single preflight** — ReviewScreen no longer runs EXPORT_PREFLIGHT before export; `LocalCsvExportService` + `ensureExportPrepJobs` is authoritative. REVIEW_OPEN backfill uses `onError` ref (no identity churn).
6. **Recoverable CSV/ZIP publish** — versioned finals, temps, validate both, compensate (delete new CSV if ZIP move fails); prior artifacts untouched.
7. **Producer wiring tests** — `runPhotoStableProducers` covers MANUAL/NOW/WHEN_CONNECTED/uploading/upload_review/flag-off; not `enqueueStablePhoto`-only.
8. **Real SQLite** — `node:sqlite` tests: CAS across two connections; v34→v35 migration + concurrent backfill PK safety.
9. **Schema** — v35 not edited; CHECK rebuild deferred; invariants enforced in repo + `validateReadyStaging`.
10. **UI** — FAILED_TERMINAL label `Prep bloqueada (N terminal)`; backfill errors surfaced.

## Root causes addressed

- Photo-id-only lease clears racing renew/claim.
- READY trusted from SQL metadata / well-formed SHA without file proof.
- Duplicate EXPORT_PREFLIGHT (UI + service).
- Destructive publish that deleted prior good CSV/ZIP before both new files succeeded.
- Policy “tests” that only called `enqueueStablePhoto`.
- Map harness presented as SQL concurrency evidence.

## Final invariants

- Backfill cannot clear a renewed/reclaimed lease (CAS `changes`).
- Strong READY ⇒ real size + real SHA match persisted values.
- Historical v34 sessions migrate additively to v35 and materialize jobs via backfill.
- Prep enqueue is independent of upload policy when the queue is wired.
- Finish awaits `onPhotoStable` Promise (enqueue), does **not** claim prep drain.
- Preflight authority is export service once.
- Partial publish never inserts export row; rolls back new CSV on ZIP failure.
- Concurrency evidence uses real SQLite.

## Evidence

| Item | Location |
|------|----------|
| CAS SQL | `exportPrepRepository.ts` `requeueExpiredLeaseInTx` |
| CAS tests | `exportPrepFencing.memory.test.ts`, `exportPrepSqlite.real.test.ts` |
| Strong READY | `validateReadyStaging.ts`, export preflight in `localCsvExportService.ts` |
| SQLite v34→v35 | `exportPrepSqlite.real.test.ts` |
| Finish deferred | `captureService.test.ts` |
| Producer wiring | `photoStableProducers.ts` + test |

## Command results

| Command | Result |
|---------|--------|
| `cd mobile && npm run typecheck` | PASS |
| `cd mobile && npm run lint` | PASS |
| `cd mobile && npm test` | PASS (47 suites / 348 tests + integration 25) |
| Export prep / SQLite suites | PASS |
| `npm run android:release` | **FAIL** — `UnknownHostException: services.gradle.org` (Gradle dist download). Environment/network; not caused by these corrections. |

## Residual risks

- JS write-gate serializes `runImmediateTransaction` in-process; true multi-connection CAS is covered, but multi-process contention on device is still native SQLite.
- `light` READY skips re-hash (intentional); EXPORT_PREFLIGHT always strong.
- Android release binary not produced in this environment.
- Phase 3 still owns full prep drain barrier on finish if required later.

## Files excluded from functional commit

Do **not** include in the functional commit:

- Root / nested `AGENTS.md` (local agent notes)
- Prior `audit/mobile-incremental-zip/*` historical dumps unrelated to this correction set (keep only this run’s `implementation-corrections-*` if publishing audit evidence)
- gitignored `review/` workflow dumps
- caches, `.gradle`, coverage, logs, binaries, generated outputs

Functional scope for commit: the 18 mobile source/test/config files listed in `implementation-corrections-status.txt`.
