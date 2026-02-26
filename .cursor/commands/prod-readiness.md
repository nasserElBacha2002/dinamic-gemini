# prod-readiness

You are a staff-level engineer evaluating production readiness of a computer vision inventory system.

Task: Produce a production-readiness assessment of this repository.

Evaluate these dimensions:
1) Reliability & failure handling (corrupt video, empty frames, model errors, timeouts).
2) Determinism & auditability (config-driven thresholds, reproducible outputs, traceability).
3) Observability (structured logs, metrics, debug artifacts, run IDs).
4) Data contracts & outputs (stable schemas, versioning, backward compatibility).
5) Performance & resource use (batching, caching, memory stability).
6) Security basics (unsafe paths, untrusted inputs, sensitive logs).
7) Deployment considerations (env config, dependencies, GPU/CPU fallback).
8) Testing maturity (unit/integration tests, smoke tests, CI hooks).

For each gap, include:
- Severity (CRITICAL/HIGH/MED/LOW)
- What breaks in production
- Concrete hardening action (minimal change preferred)
- Suggested acceptance check (how to verify it’s solved)

Output format (strict):
# Production Readiness Review

## Executive Summary
## Readiness Score (0–10) + Rationale
## Critical Gaps (must fix)
## High Priority Gaps
## Medium / Low Priority Gaps
## Recommended Hardening Roadmap (2–4 phases)
## “Go/No-Go” Checklist for a Demo
## Minimal Monitoring / Logging Spec
## Test & Validation Plan (smoke + regression)

Constraints:
- Keep recommendations practical for current project stage.
- Do not propose heavy platform work unless necessary.
- Favor stable outputs, clear configs, and robust error handling.

This command will be available in chat with /prod-readiness
