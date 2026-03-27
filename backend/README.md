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

## SQL Server configuration (canonical contract)

All DB access (API, workers, `dinamic-db-migrate`) resolves the ODBC connection string in **one** place: `src.config.resolve_sqlserver_connection_config()` / `Settings.require_sqlserver_connection_string()`.

**Supported modes** (values are trimmed):

1. **Full string:** `SQLSERVER_CONNECTION_STRING` — if set and non-empty, it wins.
2. **Split vars:** `SQLSERVER_SERVER`, `SQLSERVER_DATABASE`, `SQLSERVER_UID`, `SQLSERVER_PWD`, and optionally `SQLSERVER_DRIVER`.

If `SQLSERVER_DRIVER` is omitted, the resolver picks an installed driver in order: exact names `ODBC Driver 18/17/13 for SQL Server`, then any `pyodbc` driver name containing `SQL Server`.

**Early validation (local / CI):**

```bash
cd backend && pip install -e .
dinamic-db-migrate config-check   # or: dinamic-db-migrate doctor
```

Exits `0` when a connection string can be built, `3` when not. Output is JSON with `config_mode` (`connection_string` | `split_env` | `unset` | `incomplete_split`), `missing_env_vars`, and `driver_resolution` — **no passwords**.

On failure, exceptions include `SqlServerConfigurationError.config_mode` and `missing_env_vars`.

## Schema Migrations and Deployment Guard

This backend now uses a versioned schema guard to prevent rolling out code against an outdated DB schema.

- Versioned migrations: `src/database/migrations/versions/*.sql`
- Migration state table: `schema_migrations`
- Migration utility (from `backend/`, after `pip install -e .`):
  - `dinamic-db-migrate config-check` (run before `apply` / `validate` in CI)
  - `python scripts/db_migrate.py status|apply|validate|config-check`
  - `python -m src.database.migrations status|apply|validate|config-check`
  - `dinamic-db-migrate status|apply|validate` (console script from the install)
- CI/CD production path (recommended): run migrations via one-off ECS task inside VPC
  using `.github/scripts/run-ecs-migration-task.sh` with command
  `python scripts/db_migrate.py config-check && python scripts/db_migrate.py apply && python scripts/db_migrate.py validate`.
- Backend container image includes SQL Server runtime support (`pyodbc`, `unixODBC`, `msodbcsql18`) and fails at build-time if ODBC Driver 18 is unavailable.
- Runtime guard:
  - startup check compares DB version vs required version
  - `/ready` returns `503` when schema is incompatible
  - `/health` exposes compatibility metadata

Important env vars:

- SQL Server: see **SQL Server configuration** above. In production CI, DB creds stay in ECS task definition / secrets; GitHub runner only needs AWS/ECS metadata (task definition, container name, subnets, security groups).
- `DB_SCHEMA_SERVICE_NAME` (default: `inventory-api`)
- `DB_SCHEMA_REQUIRED_VERSION` (optional override)
- `DB_SCHEMA_GUARD_ENABLED` (default: `true`)
- `DB_SCHEMA_GUARD_BLOCK_STARTUP` (default: `true`)
- `DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC` (default: `60`)
- `DEPLOYMENT_ID` (optional deployment marker in migration history)
