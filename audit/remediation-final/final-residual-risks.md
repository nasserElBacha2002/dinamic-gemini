# Final residual risks

1. **Endpoint AuthZ coverage beyond Stage 2** — many nested/export/processing routes still rely on inventory/aisle parent checks inconsistently; expand matrix gradually.
2. **DAST not executed** — `LOCAL_ISOLATED_ONLY` lab was not attested (SQL/API not proven healthy in this session). Marked `BLOCKED_BY_ENVIRONMENT`, not PASS.
3. **Refresh token store (SEC-003)** — in-memory only; multi-worker deployments remain incorrect for logout/refresh unless sticky sessions.
4. **Mobile/FE dependency advisories** — accepted with expiry in `security-exceptions.json`; renew or upgrade before 2026-12-15.
5. **Quality gate Gitleaks via Docker (OPS-001)** — exit 126; host scan path reports findings needing manual classification.
6. **Extreme complexity deferred** — `CodeScanProcessingStrategy.process`, `StartAisleProcessingUseCase.execute`, `GlobalExternalFallbackCoordinator.process_after_internal_pass` left intact to avoid behavioral regressions.
7. **Intermittent SQL concurrent merge flake** — `test_sql_concurrent_overlapping_sets` failed once then passed twice; full suite green on final run but flake remains.
8. **Worker dual-write / legacy bridge** — Stage-8 FS+DB paths and optional legacy claim still present; documented as active compatibility, not removed.
9. **Gemini/Anthropic broad Exception at transport boundary** — narrowed for programming errors (Gemini); Anthropic still classifies from Exception.
10. **OpenAPI/docs defaults (SEC-005)** — production hardening is config/ops, not code-changed here.
