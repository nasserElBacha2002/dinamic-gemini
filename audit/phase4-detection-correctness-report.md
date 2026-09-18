# Phase 4 — Detection correctness

## Evidence source
- Device: Samsung SM-G985F (`R58N30GNF2T`)
- Completed: **5×50 C=2** (`audit/mobile-pipeline/benchmark/2026-09-18T17-02-05-907Z`)
- Partial: **1×50 C=1** (`.../2026-09-18T17-01-03-587Z`)
- Smoke concurrent 12 C=2: detection rows present; 50-set without labels_json is not authoritative

## Results (50-photo interleaved v2 prefix, C=2 run1)
- detectionExactAccuracy: **1.00** (50/50)
- detectionRecall: **1.00**
- detectionFalseNegative: 0
- detectionUnexpectedExtra: 0

Single POSITION and single ITEM detection were exact for all photos in the 50 prefix.

## Gap
- Full **2×300** detection CSVs were not completed in this iteration (device contention / overlapping pipelines).
