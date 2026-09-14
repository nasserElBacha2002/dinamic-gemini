# 11 — Phase 3 security repository handoff

## Snapshot

- commit: `7e254f35c68610931f0f2aff5bc936a52bc77b39`
- branch: `DIN-357`
- total endpoints: 222

## Technologies

- FastAPI / Uvicorn / Python 3.11+ (CI) — local audit used backend/.venv 3.13
- SQL Server (ODBC)
- React (Vite) + Expo mobile
- JWT HS256; optional X-API-Key prefixes

## Start commands (local disposable)

```bash
# API (from backend/)
uvicorn src.api.server:app --port 8000
# Do not point DAST at shared/prod instances.
```

Base URL: `http://127.0.0.1:8000`

## Auth fixtures needed

- platform_admin JWT (unbound)
- company_admin client A / client B
- Optional metrics API key if testing `/metrics`

**Never commit real secrets.** Use `.env.example` names only.

## Prioritized endpoints for external DAST

See `06-dast-priority.md` CRITICAL list (15 ops) + uploads/imports.

## Allowed vs forbidden

| Allowed | Forbidden |
|---------|-----------|
| LOCAL_SAFE authz negatives on disposable DB | Shared/prod instances |
| LOCAL_ISOLATED uploads with cleanup | Unbounded process storms with real LLM keys |
| Non-mutating OpenAPI crawl | Mutating DAST without cleanup endpoint confirmation |

## Artifacts to import

- `endpoint-inventory.json`
- `02-endpoint-inventory.csv`
- `openapi-discovered.yaml`
- `07-dast-test-cases.md`
- `03-authorization-matrix.md`

## Simulate

- LLM providers (record/replay)
- Object storage (local FS)
- SQL disposable database
