# Phase 7 — Configuration migration

| Variable vieja | Variable nueva | Acción | Compatibilidad |
| -------------- | -------------- | ------ | -------------- |
| (none removed) | — | — | — |
| `scripts.ops.reconcile_aisle` (CLI) | `inspect_aisle` | DEPRECATE → remove after 2026-12-31 | alias works until sunset |

## Audit notes

- `.env.example` remains source of documented env vars; no dual-read aliases introduced.
- Phase 7 does not delete env vars without consumer inventory across Docker/CI/secrets.
- Recommendation: next release pin Docker base image digests in `backend/Dockerfile*`.
