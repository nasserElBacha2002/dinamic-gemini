# Phase 4 — Secrets audit

## Scanners

| Tool | Status |
| ---- | ------ |
| `gitleaks` | Not installed in PATH on audit host |
| Manual pattern grep | Completed (password/token/api_key/…) |
| `.env` / credentials | `.env` gitignored; example files only |

## Findings

| ID | Finding | Real secret? | Action |
| -- | ------- | ----------- | ------ |
| S-1 | `.env.example` empty placeholders | No | Keep |
| S-2 | Test fixtures with `sk-test` / fake keys | No (clearly fake) | Keep |
| S-3 | `secrets/gcp-service-account.json` | Must not be committed | `.gitignore` + example only |
| S-4 | Docker build copying `.env` | Risk | `.dockerignore` excludes `.env`, `*.pem`, credentials |

## Logging redaction

Extended `src/pipeline/secret_redaction.py` with:

- Azure SAS query params (`sig`, `se`, `sv`, …)
- SharedAccessSignature markers
- Compact JWT-shaped strings

Mobile already redacts tokens via `mobile/src/core/logging.ts` (covered by `logging.test.ts`).

## Auth storage

| Client | Storage | Assessment |
| ------ | ------- | ---------- |
| Frontend | `localStorage` JWT session | XSS-sensitive — exception P4-003 |
| Mobile | `expo-secure-store` | Adequate for Phase 4 |

## `SECRETS_EXPOSED`

```text
SECRETS_EXPOSED=0
```

No production secrets found versioned in the working tree during Phase 4 audit.
