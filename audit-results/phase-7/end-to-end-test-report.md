# Phase 7 — End-to-end test report

## Integration (renamed)

`scripts/release/run_release_integration_validation.sh` — pytest integration/architecture suites (not E2E).

## Real E2E

`scripts/release/run_e2e_release_validation.sh` + `backend/tests/release/test_phase7_e2e_release.py`

Ephemeral SQL (0073) + deterministic `TestLLMExecutor` (no live LLM):

- claim / lease path
- cancel queued job
- retry_of unique constraint
- stale recovery + worker launch failure
- provider timeout + SQL transient retry
- API `/ready=200`

Result marker: `E2E_RELEASE_VALIDATION_OK` (script) / pytest release_e2e passed.
