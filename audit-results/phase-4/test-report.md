# Phase 4 — Test report

## Backend

| Suite | Result |
| ----- | ------ |
| `pytest -q --no-cov` (full, corrections session) | **3965 passed**, 16 skipped |
| `tests/api/test_phase4_security_hardening.py` | pass (API key Model A, CORS hosted, HSTS, redaction, TLS) |
| SQL TLS unit/runtime fixtures | pass (hosted default `TrustServerCertificate=no`) |
| Audit exception / gate unit tests | pass |

## Frontend

| Command | Result |
| ------- | ------ |
| typecheck / lint / vitest (via full audit) | pass |
| `tests/security/phase4SecretsHygiene.test.ts` | pass |
| `npm run build` + `scan-dist-secrets.cjs` | pass |

## Mobile

| Command | Result |
| ------- | ------ |
| typecheck / lint / jest (via full audit) | pass |
| Critical/High reachability doc | `mobile-dependency-reachability.md` |

## Scanners / Gate

| Tool | Result |
| ---- | ------ |
| `pip_audit` | OK |
| `bandit` | FINDINGS allowed; **blocking_high** metric gated |
| **gitleaks** (digest-pinned Docker) | OK (0 secrets) |
| security-exceptions schema/expiry | OK (7 entries) |
| `scripts/audit/run_full_audit.sh` | PASS |
| `enforce_quality_gate.py --strict` | **PASS** (`run_id=20260729T125650Z`) |

## Notes

- No Phase 5 work.
- Raw `*-stderr.txt` / `*-raw.json` under `audit-results/phase-4/` are not versioned.
