# Phase 7 — Security final report

## Tools (versions)

| Tool | How executed |
| ---- | ------------ |
| pip-audit | `backend/.venv` module |
| npm audit | frontend + mobile |
| bandit | `python -m bandit` |
| gitleaks | host binary |
| trivy | `aquasec/trivy:0.58.1` container |
| hadolint | `hadolint/hadolint:v2.12.0-alpine` (exit 0; DL3008/DL3013/DL4006 warnings) |
| shellcheck | host `/opt/homebrew/bin/shellcheck` |

Script: `scripts/release/run_security_scanners.sh` — fails closed (no `NOT_AVAILABLE`).

## Docker base digest

`python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93`

## Exceptions

None structured for Critical/High at Phase 7 close — re-run scanners on final HEAD and attach exception tickets if any Critical/High remain.
