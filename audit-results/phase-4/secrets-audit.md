# Phase 4 — Secrets audit

## Scanners

| Tool | Status |
| ---- | ------ |
| **gitleaks** (Docker image pinned by digest in `run_security_audit.sh`) | Executed; required Quality Gate tool |
| Manual pattern grep | Supplemental only (not sole evidence) |
| `.env` / credentials | `.env` gitignored; example files only |
| Frontend `dist` post-build | `frontend/scripts/scan-dist-secrets.cjs` (wired into `npm run build`) |

## Findings

| ID | Finding | Real secret? | Action |
| -- | ------- | ----------- | ------ |
| S-1 | `.env.example` empty placeholders | No | Keep |
| S-2 | Test fixtures with `sk-test` / fake keys | No (clearly fake) | Keep + gitleaks allowlist regex |
| S-3 | `secrets/gcp-service-account.json` | Must not be committed | `.gitignore` + example without PEM shape |
| S-4 | Docker build copying `.env` | Risk | `.dockerignore` excludes `.env`, `*.pem`, credentials |

## Logging redaction

`src/pipeline/secret_redaction.py`:

- Azure SAS query params preserved as `sig=[REDACTED]&se=[REDACTED]` (structure kept)
- SharedAccessSignature markers
- Compact JWT-shaped strings
- Authorization / connection-string patterns covered by tests

Mobile already redacts tokens via `mobile/src/core/logging.ts`.

## Auth storage

| Client | Storage | Assessment |
| ------ | ------- | ---------- |
| Frontend | `localStorage` JWT session | XSS-sensitive — exception P4-003 |
| Mobile | `expo-secure-store` | Adequate for Phase 4 |
| Browser API key | **Not used** (Model A — JWT only) | No `API_KEY` in `VITE_*` |

## `SECRETS_EXPOSED`

Declared only after gitleaks run in audit tooling:

```text
SECRETS_EXPOSED=0
```

(when gitleaks reports zero leaks on the scanned tracked tree).
