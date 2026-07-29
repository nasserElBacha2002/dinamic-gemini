# Phase 4 — Test report

## Backend

| Suite | Result |
| ----- | ------ |
| `pytest -q --no-cov` (full) | **3962 passed**, 16 skipped |
| `tests/api/test_phase4_security_hardening.py` | pass |
| `tests/unit/test_sqlserver_resolution.py` (TrustServerCertificate) | pass |
| Phase 3 fencing test alignment (promotion / cancel / finalization markers) | pass |

## Frontend

| Command | Result |
| ------- | ------ |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm run test -- --run` | **1223** passed |
| `tests/security/phase4SecretsHygiene.test.ts` | pass |
| `npm audit --audit-level=high` | pass (2 moderate remaining) |

## Mobile

| Command | Result |
| ------- | ------ |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm test -- --watchman=false` | pass |

## Scanners / Gate

| Tool | Result |
| ---- | ------ |
| `pip_audit --skip-editable` | 0 vulns |
| `bandit -r backend/src scripts` | FINDINGS (advisory; gate allow_findings) |
| `scripts/audit/run_full_audit.sh` | PASS |
| `enforce_quality_gate.py --strict` | **PASS** (run_id `20260729T121711Z`) |

## Notes

- Tests de promoción/finalización se alinearon a `lease_fencing_token` / `update_finalization_if_leased` (deuda de Phase 3), sin cambiar arquitectura de lease.
- `gitleaks` no disponible en PATH; secrets audit manual + `.gitignore` / `.dockerignore`.
