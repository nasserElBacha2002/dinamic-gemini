# Phase 4 — Security exceptions (generated)

Source of truth: `audit/security-exceptions.json`. Do not edit this Markdown by hand.

| finding_id | severity | component | reachability | owner | ticket | created_at | expires_at |
| ---------- | -------- | --------- | ------------ | ----- | ------ | ---------- | ---------- |
| P4-003 | high | `frontend/src/features/auth/storage.ts` | reachable | platform-security | SEC-P4-003 | 2026-07-17 | 2026-10-17 |
| P4-009 | medium | `.github/workflows/*.yml` | reachable | platform-ci | SEC-P4-009 | 2026-07-17 | 2026-10-17 |
| P4-010 | medium | `frontend/react-router-dom` | partial | frontend | SEC-P4-010 | 2026-07-17 | 2026-10-17 |
| P4-011 | high | `mobile/expo-51-transitive` | ci_build_tooling | mobile | SEC-P4-011 | 2026-07-17 | 2026-12-17 |
| P4-013 | low | `GET /health` | reachable | platform-api | SEC-P4-013 | 2026-07-17 | 2026-10-17 |
| P4-014 | low | `upload-limits` | reachable | platform-api | SEC-P4-014 | 2026-07-17 | 2026-10-17 |
| P4-020 | low | `bandit-B608` | false_positive | platform-api | SEC-P4-020 | 2026-07-29 | 2026-12-17 |

## Details

### P4-003

- **Reason:** JWT access+refresh tokens stored in localStorage (XSS risk)
- **Mitigation:** CSP/XSS hygiene; backend authz; planned httpOnly cookie migration

### P4-009

- **Reason:** GitHub Actions pinned by mutable tags (@v4) not commit SHA
- **Mitigation:** permissions contents:read; no deploy secrets on PR gate

### P4-010

- **Reason:** npm moderate advisories on RR6; RR7 major deferred
- **Mitigation:** SPA without SSR; avoid attacker-controlled navigate targets

### P4-011

- **Reason:** Critical/High npm advisories via Expo 51 CLI/Jest/eslint/tar tooling
- **Mitigation:** No npm audit fix --force; Expo major upgrade track; app runtime does not unpack untrusted tar

### P4-013

- **Reason:** Unauthenticated liveness returns schema/backend status fields
- **Mitigation:** No secrets/paths/connection strings; /ready is readiness gate

### P4-014

- **Reason:** Large default upload ceilings
- **Mitigation:** Reverse-proxy + app limits; ops documentation

### P4-020

- **Reason:** Bandit B608 on constant f-string SQL with bound ? parameters
- **Mitigation:** Identifiers static/allowlisted; values bound via pyodbc parameters

_Generated at 2026-07-29_
