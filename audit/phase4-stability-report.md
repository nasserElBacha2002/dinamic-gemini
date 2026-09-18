# Phase 4 — Stability

## Observed on completed 5×50 C=2
- crash/ANR/OOM: none reported in run statuses (all COMPLETED, pendingJobs=0)
- stuck PROCESSING: none (terminalCount=50 each run)
- LOCAL_SCAN_BUSY: not observed in completed run summaries
- pipelineErrors (correctness): 0

## Concurrent campaign hazard
Multiple Mac coordinators were launched against the same device mid-iteration; this invalidated some in-flight runs. Subsequent campaigns must use a single exclusive orchestrator.

## Thermal / battery / memory
- expo-battery: unavailable
- android thermal API: not wired
- adb `dumpsys meminfo` / `dumpsys battery`: captured before some runs under `audit/mobile-pipeline/phase4/device-*-before.txt` — treat as **available (coarse)** / not synchronized per-photo.
