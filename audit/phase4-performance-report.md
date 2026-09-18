# Phase 4 — Performance

Generated: 2026-09-18T18:32:35Z

## Controls
- workers (`exportPrepMaxWorkers`) = **2** constant
- only `scannerConcurrency` varies
- Why workers ≠ 1: barcode scans execute inside `processJob`; workers=2 keeps feed capacity so C=2 can saturate the scanner pool. Holding workers fixed isolates the A/B variable.

## Wall-clock suite totals (Mac coordinator `benchmark-runs.csv`)

| Suite | C | runs | median ms | min | max | ms/photo |
|-------|---|------|-----------|-----|-----|----------|
| 50 | 1 | 5 | 43132 | 42079 | 45412 | 862.6 |
| 50 | 2 | 5 | 43087 | 42489 | 57605 | 861.7 |
| 300 | 1 | 2 | 269810 | 269212 | 270408 | 899.4 |
| 300 | 2 | 1* | n/a (no runs.csv; env-span ≈200445 ms on-device) | — | — | — |

\* Second 300 C=2 run incomplete (coordinator SIGTERM/SIGKILL during push). Do not treat 300 C=2 wall as conclusive vs C=1.

## Per-photo scanner_processing_ms (dual correctness rows)

| Suite | C | median | p95 | n |
|-------|---|--------|-----|---|
| 50 | 1 | 325 | 457 | 250 |
| 50 | 2 | 294 | 653 | 250 |
| 300 | 1 | 320 | 546 | 600 |
| 300 | 2 | 303 | 599 | 300 |

C=2 shows a small median scanner gain on 50 (~9.5%) but **worse p95** (457→653). Suite wall-clock median is flat (43132 vs 43087).

## Concurrency observation

| Suite | configured C | maxObservedScannerConcurrency (JS) | maxObservedNativeScannerConcurrency |
|-------|--------------|--------------------------------------|-------------------------------------|
| 50 C=1 | 1 | 1 | 1 |
| 50 C=2 | 2 | **2** | **1** |
| 300 C=1 | 1 | 1 | 1 |
| 300 C=2 | 2 | **2** | **1** |

JS pool reaches 2; **native ML Kit never observes concurrency > 1**.
