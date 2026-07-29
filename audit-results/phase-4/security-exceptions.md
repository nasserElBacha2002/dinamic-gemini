# Phase 4 — Security exceptions (temporary)

Every exception must have owner, reason, reachability, mitigation, and expiry.
The Quality Gate / ops review must fail an exception past `expires_at`.

| finding_id | package/file | reason | reachability | mitigation | owner | ticket | created_at | expires_at |
| ---------- | ------------ | ------ | ------------ | ---------- | ----- | ------ | ---------- | ---------- |
| P4-003 | `frontend/src/features/auth/storage.ts` | JWT/access+refresh in localStorage (XSS risk) | Reachable | CSP/XSS hygiene; backend authz; planned httpOnly cookie migration | platform-security | SEC-P4-003 | 2026-07-17 | 2026-10-17 |
| P4-009 | `.github/workflows/*.yml` | Actions pinned by mutable tags (`@v4`) not commit SHA | Reachable (supply chain) | `permissions: contents: read`; no secrets on fork PRs by default | platform-ci | SEC-P4-009 | 2026-07-17 | 2026-10-17 |
| P4-010 | `frontend` react-router-dom ^6.30.4 | npm moderate advisories; RR7 is major breaking | Partial (SPA, no SSR) | Stay on RR6; avoid attacker-controlled navigate targets | frontend | SEC-P4-010 | 2026-07-17 | 2026-10-17 |
| P4-011 | `mobile` Expo 51 transitive (tar/xmldom/glob/…) | High/critical in npm audit; mostly CLI/Jest/eslint | Not reachable (app runtime) | No `npm audit fix --force`; Expo major upgrade dedicated track | mobile | SEC-P4-011 | 2026-07-17 | 2026-12-17 |
| P4-013 | `GET /health` | Unauthenticated liveness returns schema/backend status fields | Reachable | No secrets/paths/connection strings; `/ready` is the gate | platform-api | SEC-P4-013 | 2026-07-17 | 2026-10-17 |
| P4-014 | Upload size defaults | Large default upload ceilings | Reachable | Enforce reverse-proxy + app limits; document ops | platform-api | SEC-P4-014 | 2026-07-17 | 2026-10-17 |

## Policy

```text
CRITICAL/HIGH reachable → block merge unless fixed or exception with owner+expiry
MEDIUM → fix when low-risk; else exception
LOW/Info → advisory
false_positive → evidence in vulnerability-matrix.md
expired exception → treat as blocking finding
```

## Expired-exception check

```bash
# Manual / CI companion (Phase 4): fail if any expires_at < today
python - <<'PY'
from datetime import date
from pathlib import Path
text = Path("audit-results/phase-4/security-exceptions.md").read_text()
# rows with ISO dates in last column — keep in sync with table above
expires = ["2026-10-17", "2026-10-17", "2026-10-17", "2026-12-17", "2026-10-17", "2026-10-17"]
today = date.today()
for e in expires:
    if date.fromisoformat(e) < today:
        raise SystemExit(f"expired security exception: {e}")
print("ok: no expired exceptions")
PY
```
