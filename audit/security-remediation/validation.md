# Validation

## Environment

- Node: v22.14.0
- npm: 11.4.2
- Backend pytest: `backend/.venv/bin/pytest`

## Commands and results

| Area | Command | Result |
|------|---------|--------|
| Root install / audit | `npm install` · `npm audit` | **0** vulnerabilities |
| Frontend install | `npm install` | ok |
| Frontend typecheck | `npm run typecheck` | **pass** |
| Frontend unit tests | `npm test` | see note below |
| Frontend build | `npm run build` | **pass** (secrets scan OK) |
| safeInternalPath | `npm test -- tests/utils/safeInternalPath.test.ts` | **pass** (4) |
| RR7 regression fixes | LoginPage + AislePositions reset tests | **pass** |
| Mobile typecheck | `npm run typecheck` | **pass** |
| Mobile doctor | `npm run doctor` | **pass** (Android-only ignore of Xcode check) |
| Mobile tests | `npm test` | **pass** (core + services + integration) |
| Backend security headers | `.venv/bin/pytest tests/api/test_phase4_security_hardening.py -q` | **12 passed** |
| npm audit after | root / frontend / mobile JSON snapshots | written under `npm-audit/` |

### Frontend full suite note

Initial full `npm test` after RR7 showed 2 failures (LoginPage token assert; AislePositions filter reset). Both fixed in-product/test for RR7 behavior. **Re-run after fixes: 214 files / 1261 tests passed.**

## Security regression tests added/covered

- `safeInternalPath`: external URL, protocol-relative, javascript, backslash rejected; internal paths allowed.
- Backend headers already covered by phase4 hardening tests (not duplicated).
- No artificial “CVE presence” unit tests for lockfile-only issues.

## SAST re-run

- **Dependency SAST proxy:** `npm audit` before/after captured for all three trees.
- **Full security-agents SAST pipeline:** not re-executed as a product code change to the framework; sibling `dinamic-security-agents` remains unmodified. Operators should re-run their existing `security-audit.yaml` workflow against this tree for Semgrep/Gitleaks/Trivy confirmation.
- Expected: Critical tar/shell-quote cleared; Expo residual highs remain until SDK upgrade.

## Explicit non-goals validated

- No changes to DAST cleanup endpoint / `max_requests`.
- No mass-assignment / Pydantic `extra=forbid` flip.
- No security-agents framework edits.
