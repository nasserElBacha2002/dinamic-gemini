# Phase 4 corrections — implementation notes

## Status

`CORRECTIONS_VALIDATED` — Quality Gate `--strict` **PASS** (`run_id=20260729T125650Z`).

## API key policy (Model A)

- Public browser/mobile clients authenticate with **JWT only**.
- `API_KEY` is optional; enforced only when `API_KEY_REQUIRED_PATH_PREFIXES` is non-empty.
- `/health` and `/ready` never require an API key.
- Do **not** embed `API_KEY` in `VITE_*` or mobile bundles.
- No global middleware requiring a shared secret for SPA traffic.

## SQL TLS

- Local/test/dev: default `TrustServerCertificate=yes`.
- Hosted/unknown: default `no`; full connection strings validated (`Encrypt`, trust).
- Invalid booleans fail startup; hosted break-glass via `SQLSERVER_ALLOW_INSECURE_TRUST=true`.

## Exceptions

- Source of truth: `audit/security-exceptions.json` (versioned; not `*.json`-ignored).
- Generated MD: `audit-results/phase-4/security-exceptions.md`
- Quality Gate fails on expired/invalid/duplicate/missing fields.

## Gitleaks

- `scripts/audit/run_security_audit.sh` uses pinned image digest.
- Scans tracked working-tree files (`git ls-files`).
- Gate tool **Gitleaks** required; last run **0 secrets** (`SECRETS_SCAN_CLEAN` only after real scan).
- Example GCP SA PEM placeholder removed from `.example`.

## Bandit

- `blocking_high` metric (HIGH severity + HIGH/MEDIUM confidence) fails the gate.
- Medium/low FINDINGS remain advisory; no global `allow_findings` as phase closure for High.

## CORS / headers

- Hosted: required HTTPS origins, no localhost/wildcard/null.
- HSTS only hosted + `ENABLE_HSTS` + `FORWARDED_TRUSTED_HOSTS` (proxy TLS).

## Docker

- `COPY --chown=appuser:appuser`; uid **10001**.
- Smoke: `scripts/audit/docker_nonroot_smoke.sh` — **PASS** (API `/health`, uid 10001, tesseract spa/eng, pyzbar, worker import)

## Outputs

- Raw scanner dumps under `audit-results/phase-4/*-stderr|*-raw.json` gitignored.
- CI artifacts belong under `audit/raw/` with `run_id`.

## Validation (this correction)

| Check | Result |
| ----- | ------ |
| Backend pytest | PASS (prior full suite 3965 passed) |
| Ruff / Mypy (via full audit) | PASS |
| Gitleaks | PASS |
| Bandit | OK (FINDINGS allowed; no blocking_high) |
| pip-audit | PASS |
| Frontend / Mobile suites (via full audit) | PASS |
| `enforce_quality_gate.py --strict` | **PASS** |
| Phase 5 started? | **No** |
