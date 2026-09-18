# FINAL VERDICT

**INCONCLUSIVE** (Phase 4 not closed)

## Why not CANDIDATE_FOR_PRODUCTION
1. **PERFORMANCE** — incomplete C1 5×50 + missing comparable 300 A/B.
2. **CONCURRENCY_OBSERVED** — native `maxObservedNativeScannerConcurrency` never reached 2; JS peaked at 2 only in the 12-photo smoke.
3. **CORRECTNESS_ABSOLUTE** — recorded gate fail on domainExactAccuracy under stale multi_true expectation; expectation fixed post-run; needs re-bench.
4. **CORRECTNESS_REGRESSION** — C1 vs C2 photo-diff not completed for 300.
5. **INTEGRITY** — overlapping pipelines compromised parts of the campaign.

## C1 vs C2 (available)

### 50 photos
| metric | C1 | C2 |
| --- | --- | --- |
| wall median | n/a (1/5 runs) | see phase4-50-c2-summary.csv |
| detection accuracy | 1.00 (1 run) | 1.00 (5 runs) |
| domain accuracy (pre-fix) | 0.86 (1 run) | 0.86 (5 runs) |
| maxObserved JS | 1 | 1 (50) / 2 (smoke12) |
| maxObserved native | 1 | 1 |

### 300 photos
Not completed.

### Correctness highlights (C2 50 run1)
- Detection exact: 100%
- FP: 0; wrong pos/item/qty: 0
- FN: 2 (multi_mixed)
- multi_false rejection: 5/5

### Stability
- No crash/ANR/OOM/stuck jobs on completed C2 5×50.

## Code corrections landed (this iteration)
- `andes_interleaved_v2` global under-representation planner + band proportional floors
- Dual detection/domain correctness wired to drafts + raw detections
- exportPrepMaxWorkers=2 constant; scannerConcurrency is A/B variable
- Native C=2 DEX preflight (pull APK; no silent fallback)
- FileUriPaths UTF-8 byte decode + tests
- jobsSnapshot fence documentation/tests
- selectFixtures: interleave full set then slice
- expectedDomainOutcome: POSITION+ITEM multi_true ≠ AMBIGUOUS

## Required to close Phase 4
1. Single exclusive device campaign: 5×50 C1, 5×50 C2, 2×300 C1, 2×300 C2
2. Prove native or document Expo serialization → INVALID_EXPERIMENT for ML Kit C=2
3. Re-emit correctness CSVs with fixed expectation
4. Absolute + regression gates PASS without placeholders
