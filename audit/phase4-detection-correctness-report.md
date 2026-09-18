# Phase 4 — Detection correctness

Generated: 2026-09-18T18:32:35Z

## Experiment controls
- Device: R58N30GNF2T (SM-G985F)
- Fixture order: `andes_interleaved_v2` seed `0xa4de5302`
- `exportPrepMaxWorkers=2` held constant (feed capacity)
- A/B variable: `scannerConcurrency` ∈ {1, 2}
- Full suites use `andes_benchmark_300` (`--photos 50` = band 1 of full v2 order). Standalone `andes_benchmark_50` cannot satisfy v2 gates (2 position / 48 item).

## Detection results (exact match accuracy)

| Suite | C | detectionExactAccuracy |
|-------|---|------------------------|
| 5×50 run5 | 1 | **1.00** |
| 5×50 run5 | 2 | **1.00** |
| 2×300 run2 | 1 | **1.00** |
| 1×300 run1 | 2 | **1.00** |

Detection layer is exact across all completed A/B runs. No detection regression from C=2.

## Sequence bands (300 C=1 run2)

See `audit/phase4-sequence-bands.csv` — 6 bands, detection_exact_accuracy=1.0 in every band.
