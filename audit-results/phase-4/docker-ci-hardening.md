# Phase 4 — Docker & CI/CD hardening

## Docker

| Change | API Dockerfile | Worker Dockerfile |
| ------ | -------------- | ---------------- |
| Non-root `USER appuser` (uid 10001) | Yes | Yes |
| `chown` `/app` + `/app/output` | Yes | Yes |
| `.dockerignore` secrets/keys | Expanded | Shared `backend/.dockerignore` |

**Residual:** Base image tag `python:3.11-slim` is not digest-pinned (exception / follow-up). Read-only rootfs not enabled (writable output mounts needed).

## Compose / capabilities

No expansion of capabilities. Ports unchanged. Secrets must not be build-args.

## GitHub Actions

| Control | Status |
| ------- | ------ |
| Default `permissions: contents: read` | Present on main quality gate |
| Security job: `pip-audit` + `npm audit --audit-level=high` | Present |
| Actions pinned by commit SHA | **Not** done — exception **P4-009** |
| Secrets on external PRs | Standard GitHub Free limitations; no deploy secrets in PR gate |

## Supply chain preferences (target)

```text
npm ci
pip install with locked/constrained deps
actions by SHA (follow-up)
images by digest (follow-up)
```
