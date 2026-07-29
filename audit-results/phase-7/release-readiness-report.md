# Phase 7 — Release readiness checklist

Evidence base: HEAD `9b78950c` precondition QG PASS (`run_id=20260729T160325Z`), plus Phase 7 slice validation below.

```text
[x] HEAD limpio (precondition; dirty after Phase 7 uncommitted docs until commit)
[x] Tests backend (precondition 4028 passed; re-check smoke subset)
[x] Tests SQL integration (18 passed precondition)
[x] Frontend (1223 passed precondition)
[x] Mobile (139+10 passed precondition)
[~] Migrations (0073 tools + docs; empty-DB apply in staging pending)
[~] Rollback (documented; image/config/migration N/N-1 matrix below)
[~] Docker API (build attempted in Phase 7 validation)
[~] Docker worker (build attempted in Phase 7 validation)
[x] Smoke (scripts/release/run_smoke_tests.sh)
[x] E2E automated subset (scripts/release/run_e2e_release_validation.sh)
[x] Prometheus (promtool check+test precondition)
[x] Alerts (RecoverySchedulerFailures → implemented metrics)
[~] Security (pip_audit/bandit/gitleaks PASS; trivy/hadolint NOT_AVAILABLE)
[x] Secrets (gitleaks; .dockerignore excludes .env)
[~] Quality Gate (re-run after commit of Phase 7 docs)
[~] Backup / Restore (procedure documented; not executed against prod)
[x] Runbooks (phase-5 + phase-7)
[x] Release notes (this phase)
```

Legend: `[x]` evidenced · `[~]` partial / ops follow-up · `[ ]` open
