# 02 — Tooling inventory

Fuente principal: `docs/quality-gate.md`, `scripts/audit/*`, workflows CI, `security-audit.yaml`, manifests.

## Orchestrators

| Herramienta | Ubicación | Comando oficial | Alcance | Modifica archivos | Red / infra | Seguro local |
|-------------|-----------|-----------------|---------|-------------------|-------------|--------------|
| Full audit | `scripts/audit/run_full_audit.sh` | `bash scripts/audit/run_full_audit.sh` | Monorepo | Sí → `audit/raw/**`, `audit-status.json`, `audit-summary.md` | pip-audit/npm; Docker gitleaks | Sí (artefactos audit) |
| Enforce gate | `scripts/audit/enforce_quality_gate.py` | `…/python scripts/audit/enforce_quality_gate.py --strict` | Gate | No | No | Sí |
| Quality gate CI-parity | `scripts/quality_gate.sh` | `bash scripts/quality_gate.sh` | BE+FE(+Android opt) | Puede npm ci / dist / htmlcov | Sí | Sí con cuidado |
| Backend audit | `scripts/audit/run_backend_audit.sh` | bash | Backend | Sí raw | pip-audit | Sí |
| Frontend audit | `scripts/audit/run_frontend_audit.sh` | bash | Frontend | Sí raw | npm audit | Sí |
| Mobile audit | `scripts/audit/run_mobile_audit.sh` | bash | Mobile | Sí raw | npm audit | Sí |
| Security audit | `scripts/audit/run_security_audit.sh` | bash | Secrets | Sí gitleaks JSON | **Docker** | Sí si Docker OK |
| BE architecture | `scripts/audit/run_backend_architecture_audit.sh` | bash | Architecture | Sí raw | No | Sí |
| FE architecture | `scripts/audit/run_frontend_architecture_audit.sh` | bash | Architecture | Sí raw | Opcional jscpd | Sí |

## Backend quality / SAST

| Tool | Comando típico | Estricto | Notas |
|------|----------------|----------|-------|
| compileall | `python -m compileall src` | CI | |
| Ruff | `ruff check .` | Hard gate | check-only |
| Mypy | `mypy src` | Hard gate | |
| Pytest | `pytest` (root) | Hard gate | coverage htmlcov |
| Bandit | `bandit -r backend/src` | Findings allowed | |
| pip-audit | `pip-audit --skip-editable` | Must run | Network |
| Host gitleaks | `gitleaks detect …` | Alternativo | Usado cuando Docker falla |

## Frontend / mobile

| Tool | Comando | Gate |
|------|---------|------|
| FE typecheck | `npm run typecheck` | Hard |
| FE lint | `npm run lint` | errors block |
| FE vitest | `npm run test -- --run` | Hard |
| FE build + secret scan | `npm run build` | CI FE |
| FE check:cache / i18n | package scripts | CI / local |
| npm audit FE | `--audit-level=high` (CI) | progressive FINDINGS |
| Mobile verify | `npm run verify` | typecheck+lint+test |
| Mobile jest/lint/typecheck | package scripts | Hard |
| npm audit mobile | JSON / high | progressive; high presente |

## CI workflows

| Workflow | Rol |
|----------|-----|
| `main-quality-gate.yml` | compileall, ruff, mypy, pytest; FE; pip-audit + npm audit high |
| `develop-quality-gate.yml` | Similar develop |
| `frontend-validate.yml` | FE path filter |
| `mobile-validate.yml` | `npm run verify` + prebuild assembleDebug |
| `mobile-release.yml` | Release |
| `deploy-dev-opencloud-backend.yml` | Deploy gated |

## Security framework (external)

| Item | Estado |
|------|--------|
| `security-audit.yaml` | Config SAST (semgrep, gitleaks, osv, codeql, trivy) + DAST suites |
| `security-agents` CLI | **No vendored** en repo — NOT_CONFIGURED para esta corrida |
| Mutating DAST | Requiere confirmaciones + DB disposable — **no ejecutado** |
| ZAP | disabled in yaml |

## Release / ops (inventariados, mayormente NOT_RUN)

`scripts/release/run_security_scanners.sh` (Trivy, Hadolint, gitleaks, npm/pip), smoke/e2e/migration drills — requieren SQL disposable / Docker pesado. No ejecutados en fase 1.

## Ausencias

- No pre-commit hooks
- No Makefile/Taskfile
- No `AGENTS.md`
- `audit/security-exceptions.json` **faltante** (requerido por gate)
