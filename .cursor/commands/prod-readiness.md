# prod-readiness

You are a staff-level engineer evaluating production readiness of a system that includes an **operational platform** (v3 API, use cases, persistence, frontend) and a **computer vision pipeline**.

**Task:** Produce a production-readiness assessment of this repository.

**Evaluate these dimensions:**

1. **Reliability & failure handling**  
   - Platform: API errors, DB unavailability, use-case validation, frontend error/loading states.  
   - Pipeline: corrupt video, empty frames, model errors, timeouts.

2. **Determinism & auditability**  
   - Config-driven thresholds, reproducible outputs, traceability (e.g. track_id → evidence → decision; or job/aisle status transitions).

3. **Observability**  
   - Structured logs, metrics, debug artifacts, run IDs (platform and/or pipeline).

4. **Data contracts & outputs**  
   - API request/response stability, frontend–backend alignment, pipeline output schemas (e.g. final_result.json, errors.json), versioning, backward compatibility.

5. **Performance & resource use**  
   - API and DB load, frontend bundle and runtime; pipeline: batching, caching, memory stability.

6. **Security basics**  
   - Unsafe paths, untrusted inputs, sensitive data in logs (API, frontend, pipeline).

7. **Deployment considerations**  
   - Env config, dependencies, backend vs frontend build, DB migrations, GPU/CPU fallback for pipeline.

8. **Testing maturity**  
   - Unit/integration tests (use cases, API, repositories, pipeline stages), frontend tests if any, smoke tests, CI hooks.

For each gap include:
- **Severity** (CRITICAL / HIGH / MED / LOW)
- **What breaks in production**
- **Concrete hardening action** (minimal change preferred)
- **Suggested acceptance check** (how to verify it’s solved)

**Output format (strict):**

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

**Constraints:**  
- Keep recommendations practical for current project stage.  
- Do not propose heavy platform work unless necessary.  
- Favor stable outputs, clear configs, robust error handling, and thin API/frontend contracts.

This command will be available in chat with /prod-readiness
