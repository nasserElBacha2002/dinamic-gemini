# Phase 7 — Release readiness checklist

Evidence base: Phase 7 corrections on ephemeral SQL + digest-pinned images.

```text
[x] migrations from zero
[x] migration rollback
[x] Docker API (digest-pinned base)
[x] Docker worker (digest-pinned base)
[x] smoke (/health=200 /ready=200)
[x] real E2E (SQL + deterministic provider scenarios)
[x] Trivy (via aquasec/trivy:0.58.1 container — run in security script)
[x] Hadolint (via hadolint/hadolint:v2.12.0-alpine — warnings only, exit 0)
[x] ShellCheck (scripts/release/*.sh)
[x] backup (logical drill; physical BACKUP blocked by Docker SQL Error 3041)
[x] restore (logical SELECT INTO + API /ready=200)
[x] rollback drill N/N-1
[x] backend (precondition + release suites)
[x] SQL (integration + release E2E)
[x] frontend (precondition suites)
[x] mobile (precondition suites)
[x] gitleaks
[x] Prometheus (precondition promtool)
[x] Quality Gate PASS (strict enforce on clean HEAD)
[x] audit SHA = HEAD (verified by enforce_quality_gate)
[x] clean tree (at audit time)
```

Legend: `[x]` evidenced · `[~]` pending post-commit audit step

Close evidence: full audit after Phase 7 hardening (idempotency race fix + Vitest stability + release scripts). Re-confirm `AUDIT_SHA=HEAD` with `scripts/audit/run_full_audit.sh` on the tip commit before deploy.
