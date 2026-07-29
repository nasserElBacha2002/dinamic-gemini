# Phase 4 — Docker & CI/CD hardening

## Docker

| Change | API Dockerfile | Worker Dockerfile |
| ------ | -------------- | ---------------- |
| Non-root `USER appuser` (uid **10001**) | Yes | Yes |
| `COPY --chown=appuser:appuser` | Yes | Yes |
| Writable dirs only where needed (`/app/output`) | Yes | Yes |
| `.dockerignore` secrets/keys | Expanded | Shared `backend/.dockerignore` |
| Smoke script | `scripts/audit/docker_nonroot_smoke.sh` | same |

**Expected UID/GID:** `10001:10001` (`appuser`). Do not escalate to root to fix permissions.

**Residual:** Base image tag `python:3.11-slim` is not digest-pinned (follow-up). Read-only rootfs not enabled (writable output mounts needed).

## Compose / capabilities

No expansion of capabilities. Ports unchanged. Secrets must not be build-args.

## GitHub Actions

| Control | Status |
| ------- | ------ |
| Default `permissions: contents: read` | Present on main quality gate |
| Security job: `pip-audit` + `npm audit --audit-level=high` | Present |
| Gitleaks via audit pipeline (digest-pinned image) | Present in `run_security_audit.sh` |
| Actions pinned by commit SHA | **Not** done — exception **P4-009** |
| Raw scanner dumps in `audit-results/phase-4/` | **gitignored**; CI artifacts under `audit/raw/<run_id>` |

## Supply chain preferences (target)

```text
npm ci
pip install with locked/constrained deps
actions by SHA (follow-up)
images by digest (gitleaks done; base Python image follow-up)
```
