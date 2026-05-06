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
pip install -e "backend/[dev]"   # with dev deps (pytest, ruff, mypy, bandit, pip-audit, etc.)
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

## Local/dev worker verification

For the reference-images flow, local/dev closure depends on the worker using the current backend code and local artifact paths without fake S3 requirements.

### Expected local/dev behavior

- `ARTIFACT_STORAGE_PROVIDER=local` works without an S3 bucket.
- `python -m src.jobs.run_worker_dev` watches the backend directory and restarts the standard worker entrypoint on code changes.
- The standard worker still logs the active storage mode through `src.jobs.run_worker.main()`.
- A local run with reference images should resolve artifacts from the local filesystem and persist the same `visual_reference_context` / execution-log traceability used in other environments.

### Smoke verification checklist

Run from the repository root:

```bash
# 1) Start the API and dev worker
uvicorn src.api.server:app --reload --port 8000
python -m src.jobs.run_worker_dev

# 2) Create an inventory and upload 1-3 reference images
# 3) Create an aisle and upload aisle assets
# 4) Start aisle processing
```

Verify all of the following:

- worker log includes `Worker dev reloader watching .../backend`
- worker log includes `Worker artifact storage: provider=local`
- processing completes without requiring `artifact_s3_bucket`
- job execution log contains the Gemini request payload with `visual_reference_attachments`
- aisle status/list exposes `latest_job.reference_usage`
- replacing or deleting references changes only future jobs, not historical `job.result_json`

### Regression tests that support this checklist

- `backend/tests/jobs/test_run_worker_dev.py`
- `backend/tests/jobs/test_run_worker_entrypoint.py`
- `backend/tests/api/test_v3_stored_artifact_access_unit.py`
- `backend/tests/infrastructure/pipeline/test_v3_job_executor_input_resolution.py`
- `backend/tests/infrastructure/pipeline/test_v3_job_executor_phase5.py`

## Docs

See the repository root **README.md** and **docs/** for full project documentation.

## SQL Server configuration (canonical contract)

All DB access (API, workers, `dinamic-db-migrate`) resolves the ODBC connection string in **one** place: `src.config.resolve_sqlserver_connection_config()` / `Settings.require_sqlserver_connection_string()`.

**Supported modes** (values are trimmed):

1. **Full string:** `SQLSERVER_CONNECTION_STRING` — if set and non-empty, it wins.
2. **Split vars:** `SQLSERVER_SERVER`, `SQLSERVER_DATABASE`, `SQLSERVER_UID`, `SQLSERVER_PWD`, and optionally `SQLSERVER_DRIVER`.

If `SQLSERVER_DRIVER` is omitted, the resolver picks an installed driver in order: exact names `ODBC Driver 18/17/13 for SQL Server`, then any `pyodbc` driver name containing `SQL Server`.

**`SQLSERVER_DRIVER` — expected value:** The **exact** driver name from `pyodbc.drivers()` (e.g. **`ODBC Driver 18 for SQL Server`**). The default **Dockerfile** / **Dockerfile.worker** install **msodbcsql18** for the image architecture (amd64 or arm64 via Microsoft’s multi-arch Debian repo — do not pin `[arch=amd64]` in apt). Omit `SQLSERVER_DRIVER` to auto-pick among installed Microsoft drivers. *missing `SQLSERVER_DRIVER`* / *Schema guard skipped* mean incomplete split vars or no matching driver in **that** environment (host vs container differ: the container must have the driver inside the image).

**Docker vs host SQL Server:** Inside a container, **`localhost` / `127.0.0.1` refer to the container**, not your Mac/Windows/Linux host. If SQL Server runs on the host and your `.env` uses loopback, keep that `.env` for native runs; in Docker the resolver **rewrites** loopback `SQLSERVER_SERVER` / `SERVER=` in `SQLSERVER_CONNECTION_STRING` to **`host.docker.internal`** when `/.dockerenv` is present (override with **`SQLSERVER_DOCKER_HOST`** e.g. `172.17.0.1` on Linux). **`backend/docker-compose.yml`** adds `extra_hosts: host.docker.internal:host-gateway` so Linux Docker can resolve that name. Use an explicit port when needed: **`host.docker.internal,1433`** (ODBC `SERVER` syntax).

**Early validation (local / CI):**

```bash
cd backend && pip install -e .
dinamic-db-migrate config-check   # or: dinamic-db-migrate doctor
```

Exits `0` when a connection string can be built, `3` when not. Output is JSON with `config_mode` (`connection_string` | `split_env` | `unset` | `incomplete_split`), `missing_env_vars`, `driver_resolution`, and when ok **`sqlserver_connect_target`** (ODBC `SERVER=` value after Docker loopback remap) — **no passwords**.

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
- **DEV (OpenCloud):** migrations are run on the Ubuntu server (or in a one-off container), not by GitHub Actions — see `docs/deployment/DEV-OPENCLOUD.md`.
- **AWS ECS (archived):** former one-off migration task script lives under `deployment/archive/aws-ecs-dev-legacy/scripts/run-ecs-migration-task.sh` for reference if a future production pipeline uses ECS again.
- Backend container images install **`pyodbc`**, **unixODBC**, and **Microsoft ODBC Driver 18** (`msodbcsql18`) using the architecture-native package from Microsoft’s Debian 12 repo (same driver name **`ODBC Driver 18 for SQL Server`** inside the container as on a typical Linux host).
- Runtime guard:
  - startup check compares DB version vs required version
  - `/ready` returns `503` when schema is incompatible
  - `/health` exposes compatibility metadata

Important env vars:

- SQL Server: see **SQL Server configuration** above. On the DEV OpenCloud server, credentials live in the **repository root** `.env` (e.g. `/opt/dinamic/dinamic-gemini/.env`), loaded by `backend/docker-compose.yml` — not committed. A future production setup may use a different secret store (e.g. ECS secrets); `main` is not treated as production in this repo.
- `DB_SCHEMA_SERVICE_NAME` (default: `inventory-api`)
- `DB_SCHEMA_REQUIRED_VERSION` (optional override)
- `DB_SCHEMA_GUARD_ENABLED` (default: `true`)
- `DB_SCHEMA_GUARD_BLOCK_STARTUP` (default: `true`)
- `DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC` (default: `60`)
- `DEPLOYMENT_ID` (optional deployment marker in migration history)
