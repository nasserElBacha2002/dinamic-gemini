# Phase 4 — Performance

## Experiment controls
- exportPrepMaxWorkers **fixed at 2** (feed). Scans only run inside `ExportPrepQueue.processJob`; workers=1 cannot observe scanner C=2.
- Measured variable: scannerConcurrency 1 vs 2.
- Order: `andes_interleaved_v2` seed `0xa4de5302`.

## Completed data
### 5×50 C=2 wall clocks (ms)
See `phase4-50-c2-summary.csv` (median of five COMPLETED runs).

### 5×50 C=1
Only **1/5** runs completed before overlapping pipelines interrupted the campaign.

### 300
Not completed to a comparable C1 vs C2 pair in this iteration.

## Concurrency observation
- Smoke 12 C=2: `maxObservedScannerConcurrency=2` (JS), `maxObservedNativeScannerConcurrency=1`.
- 5×50 C=2: `maxObservedScannerConcurrency=1`, native=1 → **CONCURRENCY_NOT_OBSERVED** for native ML Kit parallelism (Expo AsyncFunction `detectBarcodes` appears to serialize; JS slots can still peak at 2 while waiting).

## Verdict on performance gate
**INCONCLUSIVE** — missing balanced C1 medians and 300 confirmation; native C=2 not observed.
