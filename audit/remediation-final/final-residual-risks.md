# Final residual risks (post-corrections)

1. **`REMEDIATION_PARTIALLY_COMPLETED`** — quality gate may still FAIL on Gitleaks Docker tooling; DAST not run; Semgrep registry ruleset not downloadable in this environment (local ruleset executed instead).
2. **Tenant surface beyond Stage 2** — jobs/artifacts/revisions/results/overrides/reprocess/analytics lack full dynamic AuthZ proof (~140 routes). See `final-tenant-coverage-matrix.md`.
3. **TEST-002** remains `PARTIALLY_IMPLEMENTED_PENDING_DAST`.
4. **Local `secrets/*.json`** — gitignored service-account file may exist on disk; never commit; rotate if ever leaked.
5. **SEC-003/004/005** deferred or accepted as before.
6. **Complexity / code smells** deferred (not fixed this close-out).
7. **npm mobile highs** accepted via `security-exceptions.json` until 2026-12-15.
8. Merge concurrency hardening (aisle UPDLOCK, SERIALIZABLE, deadlock→conflict) reduces races; remaining deadlocks surface as `PositionMergeConflictError` (retryable by client).
