# Phase 4 — Domain correctness

## Results (5×50 C=2, run1 summary)
- domainExactAccuracy (pre-fix of POSITION+ITEM multi_true expected outcome): **0.86**
- falsePositives: 0
- falseNegatives: 2 (multi_mixed keep-valid misses)
- wrongPosition / wrongItem / wrongQuantity: 0
- multi_false correctRejections: 5/5
- multi_true: expectedOutcome was incorrectly set to AMBIGUOUS for POSITION+ITEM pairs; app correctly RESOLVED item (and detection saw both). Classifier/expectation fix applied in code after the run.

## Absolute gate
- Failed on overall domainExactAccuracy 0.86 < 0.95 under the old multi_true expectation.
- Single POSITION / single ITEM scenario accuracies were 1.00.

## Gap
- Re-score after expectation fix + complete C1 5×50 and 300 A/B required before production verdict.
