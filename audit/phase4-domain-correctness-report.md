# Phase 4 — Domain correctness

Generated: 2026-09-18T18:32:35Z

## Absolute gate (domainExactAccuracy ≥ 0.95)

| Suite | C | domainExactAccuracy | Gate |
|-------|---|---------------------|------|
| 5×50 (last run) | 1 | **0.96** | PASS |
| 5×50 (all 5 runs) | 2 | **0.86** | FAIL (all runs) |
| 2×300 | 1 | **0.877** | FAIL |
| 1×300 | 2 | **0.877** | FAIL |

## Material C=2 regression on 50-photo suite
- C=1: domainExact=48/50 (0.96), ambiguousExpected=0
- C=2: domainExact=43/50 (0.86), ambiguousExpected=5, ambiguousCorrect=0
- Detection remains 1.0; failures are domain/ambiguity outcomes under concurrency 2.

## 300-photo
- C=1 and C=2 run1 match at domainExactAccuracy=0.877 (263 domain exact, 30 correct rejections, 7 FN, 30 ambiguous expected / 0 correct).
- Absolute gate fails for both; C=2 does not improve domain correctness at scale.

Artifacts: `phase4-correctness-diff.csv`, `phase4-300-c*-run*-correctness*.csv/json`.
