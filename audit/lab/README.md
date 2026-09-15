# Disposable Phase 4B lab (Dinamic Gemini)

**Local-only, fail-closed, disposable.** Never use these files for DEV, staging, or production.

This lab provides:

- Loopback SQL Server on `127.0.0.1:14333` (avoids host collisions on 1433/1435)
- Local filesystem artifact storage under `audit/lab/data/output`
- Mocked LLM (real provider keys refused)
- Seeded tenants A/B + fixture JWTs
- `GET /lab/health` attestation for security-agents EnvironmentAttestation

## Prerequisites

- Docker Desktop (image `mcr.microsoft.com/mssql/server:2022-latest`; compose sets `platform: linux/amd64` for Apple Silicon)
- **ODBC Driver for SQL Server** on the host (required for migrate / seed / uvicorn).
  - This machine commonly has Driver **17** (`odbcinst -q -d`). `.env.lab.example` defaults to 17.
  - For Driver 18: `brew tap microsoft/mssql-release && brew install msodbcsql18 mssql-tools18`, then set `SQLSERVER_DRIVER='ODBC Driver 18 for SQL Server'`.
  - Confirm: `odbcinst -q -d`
- Backend venv (`backend/.venv`)
- Copy env template (always **source** lab env *before* starting Python so it wins over developer `.env`):

```bash
cp audit/lab/.env.lab.example audit/lab/.env.lab
```

Admin password for the fixture hash in `.env.lab.example` is `LabAdmin!Only` (lab-only).

`GEMINI_API_KEY=lab-fixture-only` is intentional (matches `LAB_FIXTURE_KEY_MARKER`) so AppSettings can load without real providers. `EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false` overrides a typical developer `.env` Claude fallback.

## Quick start

```bash
# 0) Preflight (fail-closed)
bash audit/lab/scripts/lab_preflight.sh

# 1) Start SQL
bash audit/lab/scripts/lab_up.sh

# 2) Bootstrap schema (schema.sql) + migrate markers — do NOT cold-apply 0001→N alone
#    (0001 is metadata-only; see fold_migrations_into_schema.py).
bash audit/lab/scripts/lab_bootstrap_schema.sh

# 3) Seed (idempotent)
cd backend
set -a && source ../audit/lab/.env.lab && set +a
.venv/bin/python ../audit/lab/scripts/seed_lab.py
cd ..

# 4) Run API on uncommon loopback port (host uvicorn — recommended on Mac)
cd backend
set -a && source ../audit/lab/.env.lab && set +a
.venv/bin/uvicorn src.api.server:app --host 127.0.0.1 --port 18080
```

Attestation:

```bash
curl -sS "http://127.0.0.1:18080/lab/health?audit_run_id=${LAB_RUN_ID:-demo-run}"
```

Status / reset / down:

```bash
bash audit/lab/scripts/lab_status.sh
bash audit/lab/scripts/lab_reset.sh          # recreate volume + bootstrap + seed
bash audit/lab/scripts/lab_down.sh
bash audit/lab/scripts/lab_down.sh --purge   # also delete named volume
```

## Design notes

| Concern | Lab behavior |
| --- | --- |
| Bind | SQL `127.0.0.1:14333` only; API `127.0.0.1:18080` |
| Storage | `ARTIFACT_STORAGE_PROVIDER=local` under `audit/lab/data/output` |
| LLM | `LAB_LLM_MOCKED=true`; non-fixture API keys refused |
| SQL fallback | `V3_ALLOW_IN_MEMORY_FALLBACK=false` |
| Compose | SQL only — API on host avoids Mac ODBC-in-container pain |
| Lock | `audit/lab/.lab.lock` for reset |
| Secrets | `.env.lab`, tokens, outputs gitignored |

## Schema bootstrap note

Clean install path (from `fold_migrations_into_schema.py`):

1. `bash audit/lab/scripts/lab_bootstrap_schema.sh` → applies `backend/src/database/schema.sql`, then `db_migrate.py apply`
2. Seed

On this tree, a cold `db_migrate apply` from empty (0001→N) fails because **0001 is metadata-only**. If `schema.sql` also fails FK ordering on apply, use a **schema-only clone** from a local disposable/test database (same pattern as `scripts/release/validate_migrations_from_zero.sh`) — never clone from shared DEV/staging/prod.

## Admin password hash

```bash
cd backend
.venv/bin/python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['pbkdf2_sha256']).hash('LabAdmin!Only'))"
```

Put the hash in `ADMIN_PASSWORD_HASH` inside `.env.lab` (example already has a fixture hash).

## Forbidden

- Pointing lab scripts at non-loopback SQL
- Real Gemini/OpenAI/Anthropic keys or public provider base URLs
- S3/GCS artifact providers
- Committing `.env.lab`, `fixture-tokens.json`, or lab outputs
- Using this stack against shared DEV/staging/prod data
