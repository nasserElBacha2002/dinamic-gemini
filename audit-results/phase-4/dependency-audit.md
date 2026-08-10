# Phase 4 — Dependency audit

## Python (`pip_audit`)

| Result | Detail |
| ------ | ------ |
| Exit | 0 |
| Vulnerabilities | **0** |
| Action | No Python dependency bumps required for CVE closure |

Evidence: `audit-results/phase-4/pip-audit-raw.json`

## Frontend (`npm audit`)

| Severity | Count | Notes |
| -------- | ----: | ----- |
| Critical | 0 | |
| High | 0 | CI uses `--audit-level=high` |
| Moderate | 2 | `react-router` / `react-router-dom` (RR6 advisories) |
| Low | 0 | |

**Decision:** Do **not** force-upgrade to React Router 7 (breaking). Exception **P4-010** until dedicated FE routing migration. SPA has no SSR hydration path for the SSR-oriented advisory.

## Mobile (`npm audit`)

| Severity | Approx | Notes |
| -------- | -----: | ----- |
| Critical | ≥1 | `tar` via tooling |
| High | many | Expo 51 / Jest / eslint transitive |
| Moderate/Low | many | |

**Reachability:** Dev/tooling and Expo CLI paths dominate. App runtime uses SecureStore for tokens; no user-controlled tar extraction identified.

**Decision:** No Expo 51→57 / RN major migration in Phase 4. Exception **P4-011** with Expo upgrade track.

## Docker base images

| Image | Pinning | Notes |
| ----- | ------- | ----- |
| `python:3.11-slim` | Floating minor tag | Prefer digest pin in follow-up; non-root USER added |

## Lockfiles

| Area | Lock / constraints | CI install |
| ---- | ------------------ | ---------- |
| Backend | `pyproject.toml` + editable install | `pip install -e ".[dev]"` |
| Frontend | `package-lock.json` | `npm ci` |
| Mobile | lockfile present | `npm ci` in mobile workflows |

## Abandoned / unused

No unused direct Python packages removed in this phase (pip_audit clean; no dead-import scan required for CVE closure).
