# Phase 4 — Final report (scannerConcurrency A/B)

Generated: 2026-09-18T18:32:35Z  
**Amended: 2026-09-18T19:35:00Z** (post critical-corrections smoke)

## FINAL VERDICT

### Current (post–Coroutine bridge fix) — `INCONCLUSIVE`

Supersedes the pre-fix campaign verdict below for **native concurrency engagement**.

| Gate | Status |
|------|--------|
| Native C=2 observed | **PASS** — smoke 12 C2: `maxObservedNativeScannerConcurrency=2` (dirs `2026-09-18T19-26-03-404Z`, also 3-photo `18-28-59-546Z`) |
| Domain absolute on smoke 12 | **FAIL** — 91.7%; residual FN `242_multi_mixed.jpg` (Andes POSITION `exact_length=13` vs fixture ASP len 17) |
| Full exclusive 5×50 + 2×300 after fix | **NOT COMPLETED** |

Do **not** flip production default to `scannerConcurrency=2` until profile length is corrected and a post-fix exclusive campaign closes performance + domain gates.

Evidence detail: `audit/phase4-critical-corrections-validation.md`.

---

### Historical (pre–Coroutine fix campaign) — superseded for native engagement

`REJECTED_NO_NET_BENEFIT_DOMAIN_REGRESSION_NATIVE_NOT_ENGAGED`

That campaign (summarized by [Run Phase4 device benches](154bf66a-82bc-4635-94ba-2e0581f10f7b)) measured **JS** C=2 with **native still serialized** (`runBlocking` on Expo modulesQueue). Its wall/domain numbers remain valid **only** as a pre-fix baseline — they are **not** evidence about ML Kit concurrency=2.

## One-line rationale (historical)

C=2 engages the JS scanner pool (maxObserved=2) but never native ML Kit (maxObservedNative=1); 50-suite wall-clock is flat while domainExactAccuracy regresses 0.96→0.86; no production flip.

## Controls (held constant)

| Knob | Value | Role |
|------|-------|------|
| exportPrepMaxWorkers | **2** | Feed capacity into processJob |
| scannerConcurrency | 1 vs 2 | Sole A/B variable |
| fixture order | andes_interleaved_v2 / 0xa4de5302 | Deterministic mix |
| device / APK | R58N30GNF2T / debug with setBarcodeScanConcurrency | Fixed |

Why workers ≠ 1: scans run inside `processJob`; workers=1 would starve the scanner pool and confound C=1 vs C=2. workers=2 keeps feed independent of the measured variable.

## Evidence summary

1. **Native concurrency (historical campaign)** — maxObservedNativeScannerConcurrency=1 for all C=2 runs despite JS maxObs=2 (bridge serialization; fixed later via suspend `Coroutine` AsyncFunction).
2. **Native concurrency (post-fix smoke)** — maxObservedNative=2 on C2 smoke 12; experiment can now measure ML Kit overlap.
3. **No net wall-clock win on historical 5×50** — median 43132 (C1) vs 43087 (C2) under native=1.
4. **Domain regression on historical 5×50** — 0.96 → 0.86; absolute gate fails all C2 50 runs (expectation/profile issues; residual multi_mixed FN after carve-out tied to POSITION `exact_length`).
5. **Detection OK** — exact accuracy 1.0 throughout those runs.
6. **300 C=2 incomplete historically** — only 1/2 runs completed (coordinator killed).

## Production recommendation

Do **not** flip production default to scannerConcurrency=2.

## Key artifact paths

- `audit/phase4-critical-corrections-validation.md` (authoritative for post-fix native=2 smoke)
- `audit/phase4-50-c1-summary.csv`, `audit/phase4-50-c2-summary.csv` (historical pre-fix campaign)
- `audit/phase4-300-c1-summary.csv`, `audit/phase4-300-c2-summary.csv`
- `audit/phase4-correctness-diff.csv`
- `audit/phase4-*-report.md`, `audit/phase4-final-validation.md`
- Logs: `audit/mobile-pipeline/phase4/`
- Bench dirs: `audit/mobile-pipeline/benchmark/`
