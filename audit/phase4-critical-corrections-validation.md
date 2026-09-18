# Phase 4 critical corrections — validation

Date: 2026-09-18  
Device: R58N30GNF2T (SM-G985F)  
Commit (dirty tree): see `phase4-critical-corrections-status.txt`

## Fixes applied (code)

1. **POSITION + false domain carve-out** (`localCodeScanStrategy.ts`)  
   When supplier POSITION is VALID and ITEM is not, strip POSITION from consolidator MULTIPLE path, reject false leftovers, preserve POSITION.  
   Does **not** enter when a valid supplier ITEM is also present (multi_true).

2. **Native ML Kit concurrency** (`CaptureForegroundModule.kt` + `LocalBarcodeDetector.kt`)  
   - Replaced `runBlocking(Dispatchers.IO)` with Expo `AsyncFunction … Coroutine` suspend body.  
   - Per-call ML Kit scanner (no shared `AtomicReference`).  
   - `delay(5)` instead of `Thread.sleep`.  
   - `resetBarcodeScanConcurrencyStats` / `resetObservedConcurrencyStats` (idle-only).  
   - Hard clamp concurrency ∈ {1,2}.

3. **JS reset** per run: `resetConcurrencyStats()` + native reset in `benchmarkRunner`.

4. **jobsSnapshot revision fence**  
   `ExportPrepQueue.sessionJobsRevision` bumped on create/requeue/invalidate; consume requires matching `jobsSnapshotRevision` (fail-closed `revision_drift` / `revision_unchecked`).

5. **Harness** (`benchmark-pipeline.cjs`)  
   - Exclusive PID device lock  
   - `exportPrepMaxWorkers=2` constant; A/B only `scannerConcurrency`  
   - Abandoned RUNNING reclaim (`ABANDONED_BY_HOST`)  
   - Standalone `--photos >= 12` uses real 12–20 smoke (not forced to 3)  
   - `campaignComplete` gate for final report  
   - Split fixture/performance band CSVs; no 50→300 metric copy  
   - `.gitignore` hygiene for runtime evidence

6. **Regression tests**  
   POSITION+false (BAD/FAKE/POSX), fixture-like `ASP-A05-B01-P03-R+BAD0002`, ITEM+false, POSITION+ITEM, jobsSnapshot revision drift, Android concurrency/reset/clamp.

## Device evidence (smoke)

| Arm | photos | configured | maxJs | maxNative | detection | domain | notes |
|-----|--------|------------|-------|-----------|-----------|--------|-------|
| C1  | 12     | 1          | 1     | 1         | 100%      | 91.7%  | FN: `242_multi_mixed.jpg` |
| C2  | 12     | 2          | 2     | **2**     | 100%      | 91.7%  | Same FN; **native overlap proven** |

Dirs: `2026-09-18T19-25-46-643Z` (C1), `2026-09-18T19-26-03-404Z` (C2)

## Residual domain FN (not ML Kit / not concurrency)

Unit tests with ASP+BAD pass under **test** POSITION profiles (no `exact_length: 13`).

On-device Andes POSITION profile (`7e62caee…` v3):

- `expected_prefix=ASP`, `payload_structure=SIMPLE`, **`exact_length=13`**
- Fixture codes are **17** chars (`ASP-A05-B01-P03-R`, `ASP-A01-B01-P01-L`, …)

`LABEL_LENGTH_MISMATCH` → `supplierPosition` never `VALID` → carve-out does not run → `MULTIPLE_DISTINCT_CODES` leaves empty accepted → `FALSE_NEGATIVE` on multi_mixed POSITION+false.

Position-only rows can still “pass” dual correctness via accepted raw/product heuristics with `actualPosition=null`; mixed POSITION+false does not.

**Follow-up (explicit approval required):** update Andes POSITION profile `exact_length` to **17** (or null) to match bay-segment fixtures — data/config fix, not a global rule change for gaming fixtures.

## Tests executed

See `audit/phase4-critical-corrections-tests.txt`  
Gradle `:capture-foreground-service:testDebugUnitTest` BUILD SUCCESSFUL (FileUriPaths UTF-8 + concurrency).

## Campaign 5×50 / 2×300

Smoke gate **native=2 PASS**. Long exclusive campaign launches were interrupted by host process death / stale RUNNING / overlapping coordinators; reclaim + lock added. **Full 5×50 and 2×300 not completed in this iteration** — must re-run with durable host (survives agent session) after profile length fix for domain gate.

## FINAL VERDICT (this iteration)

**INCONCLUSIVE** for production candidacy of C=2:

- Native concurrency experiment is now **valid** (maxObservedNative=2 observed).  
- Domain gate not green on controlled smoke (`242` residual profile mismatch).  
- Performance campaign incomplete.

Do **not** interpret prior C1/C2 wall times as ML Kit C=2 evidence from before the Coroutine bridge fix.
