# Phase 4 — Stability

Generated: 2026-09-18T18:32:35Z

## Smoke
- 3 photos C=1: EXIT 0, `SMOKE_PASSED_INSTRUMENTATION_VALIDATED`
- 3 photos C=2: EXIT 0, `NATIVE_CONCURRENCY_PREFLIGHT_OK` (dex search)
- 12 photos C=2: EXIT 0, JS maxObservedScannerConcurrency=2, native=1

## Full suite exits
- 5×50 C=1: EXIT 0 (retry; all 5 COMPLETED)
- 5×50 C=2: EXIT 0 (all 5 COMPLETED; absolute correctness WARN each run)
- 2×300 C=1: EXIT 0 (both COMPLETED; absolute correctness WARN)
- 2×300 C=2: **incomplete** — run1 COMPLETED then coordinator killed (143/137); second run not finished. Also earlier ENOBUFS on APK pull (mitigated via local-debug-apk preflight).

## Resource telemetry
- `expo-battery_not_installed`; thermal API not wired
- meminfo/batterystats snapshots: `audit/mobile-pipeline/phase4/device-resources-{before,after}.txt` — mark **unavailable/unreliable** for energy claims

## Correctness stability
- C=2 50-suite domain accuracy stuck at 0.86 across all 5 runs (deterministic regression vs C=1 0.96)
