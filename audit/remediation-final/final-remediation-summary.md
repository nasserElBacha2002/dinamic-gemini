# Final remediation summary

**Status:** `REMEDIATION_COMPLETED_WITH_RESIDUAL_RISKS`  
**Date (UTC):** 2026-09-15  
**Branch:** `DIN-357` @ `f6ad26c29e749238a5017a05f9cf0df24f3c08a2` (+ uncommitted remediation)

## What closed in this phase

1. **Stage 2 tenant isolation** remained closed (policies, principal-required use cases, atomic SQL soft-delete, JWT HTTP + SQL integration suites green).
2. **ARCH-001 / ARCH-002** fixed:
   - `PROVIDER_IMAGE_MANIFEST_ORDER_KEY` moved to `domain/execution_image_manifest.py`; domain builder no longer imports pipeline.
   - `LlmCostSnapshotResponse` moved to `application/schemas/llm_cost_snapshot.py`; API re-exports; application no longer imports API.
   - Architecture import-boundary tests added under `tests/architecture/`.
3. **Error / SQL triage:** priority B608 candidates classified (none `REQUIRES_FIX`); cleanup identifiers allowlisted; Gemini retry no longer retries programming errors.
4. **Test hygiene:** JWT `auth_env` restore fixed; aisle wiring stub implements `soft_delete_many_for_scope`; full backend suite **5319 passed**.
5. **`audit/security-exceptions.json`** created for documented dependency exceptions (SEC-006/007).

## Validation snapshot

| Gate | Result |
|------|--------|
| Backend pytest | PASS (5319 passed, 4 skipped) |
| Ruff | PASS |
| Mypy | PASS |
| Frontend lint / typecheck / vitest | PASS |
| Mobile lint / typecheck / jest | PASS |
| Full audit script | FAIL tooling (Gitleaks Docker exit 126; earlier pytest flake); see residual |
| DAST LOCAL_ISOLATED | `BLOCKED_BY_ENVIRONMENT` (lab env file present; SQL/API lab not attested running this session) |

## Complexity

Large orchestrators (`CodeScanProcessingStrategy.process`, `StartAisleProcessingUseCase.execute`, global fallback coordinator) **DEFERRED** — regression risk exceeds benefit in final close-out. Feasible later extracts documented in `final-residual-risks.md`.

## Classification rationale

P0/P1 AuthZ + architecture boundaries verified with tests; residual AuthN/FE/mobile deps, DAST pending, intermittent concurrent SQL flake, and quality-gate Docker Gitleaks failure are explicit residuals — not silent success claims.
