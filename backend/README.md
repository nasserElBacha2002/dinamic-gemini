# Backend — Dinamic Inventory

Python backend for the Dinamic Inventory system: API (FastAPI), application layer, pipeline, jobs, and persistence.

## Layout

- **`src/`** — Python package (imports stay `src.*`). API, domain, application use cases, infrastructure, pipeline, jobs, config.
- **`tests/`** — Backend tests.
- **`configs/`** — Backend config files (optional).
- **`scripts/`** — Backend utility scripts (e.g. `create_aruco.py`).

## Install

From the **repository root**:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e backend/
pip install -e "backend/[dev]"   # with dev deps (pytest, black, ruff)
```

## Run

From the **repository root** (so `.env` and `output/` paths work as before):

```bash
# API server
uvicorn src.api.server:app --reload --port 8000

# CLI
python -m src.app video.mp4 --video-id VID_001
```

Or use the root dev script to run backend + frontend together:

```bash
./dev.sh
```

## Tests

From the **repository root** (recommended; uses root `pytest.ini` and coverage):

```bash
pytest
```

From this directory:

```bash
cd backend && pytest
```

## Docs

See the repository root **README.md** and **docs/** for full project documentation.

## Schema Migrations and Deployment Guard

This backend now uses a versioned schema guard to prevent rolling out code against an outdated DB schema.

- Versioned migrations: `src/database/migrations/versions/*.sql`
- Migration state table: `schema_migrations`
- Migration utility:
  - `python scripts/db_migrate.py status`
  - `python scripts/db_migrate.py apply`
  - `python scripts/db_migrate.py validate`
- Runtime guard:
  - startup check compares DB version vs required version
  - `/ready` returns `503` when schema is incompatible
  - `/health` exposes compatibility metadata

Important env vars:

- `SQLSERVER_CONNECTION_STRING`
- `DB_SCHEMA_SERVICE_NAME` (default: `inventory-api`)
- `DB_SCHEMA_REQUIRED_VERSION` (optional override)
- `DB_SCHEMA_GUARD_ENABLED` (default: `true`)
- `DB_SCHEMA_GUARD_BLOCK_STARTUP` (default: `true`)
- `DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC` (default: `60`)
- `DEPLOYMENT_ID` (optional deployment marker in migration history)
