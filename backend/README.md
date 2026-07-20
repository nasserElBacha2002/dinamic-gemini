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

### Aisle code scan (pyzbar / zbar)

The sync QR/barcode scanner runs in the **API** process only (not the worker). The Docker API image installs `libzbar0` via `backend/Dockerfile`; `backend/Dockerfile.worker` does not include it unless scanner execution moves to a worker in a future phase.

For **local development** (macOS), install the native zbar shared library in addition to Python `pyzbar`:

```bash
brew install zbar
```

Validate the runtime:

```bash
cd backend
python -c "from pyzbar.pyzbar import decode; print('pyzbar-ok')"
```

If this fails with `Unable to find zbar shared library`, install zbar as above and restart the API.

### Internal OCR (Tesseract) — Phase 4

`INTERNAL_OCR` runs in **on-demand workers**. Locally (`./dev.sh`) those workers use the host Python process, so the **Tesseract binary** must be on `PATH`. On OpenCloud DEV, workers spawn **inside the API container**, so `backend/Dockerfile` installs `tesseract-ocr` + `tesseract-ocr-spa` + `tesseract-ocr-eng` (same packages as `Dockerfile.worker`).

**Local macOS:**

```bash
brew install tesseract
brew install tesseract-lang   # includes spa + eng traineddata
```

Validate:

```bash
tesseract --version
cd backend && .venv/bin/python -c "import pytesseract; print(pytesseract.get_tesseract_version()); print(pytesseract.get_languages())"
```

If OCR jobs fail with `tesseract is not installed or it's not in your PATH`, install as above and restart `./dev.sh`.

### Manual maintenance backfills

Backfills are explicit one-shot commands and do not run automatically on API startup.

```bash
# A5: ensure legacy/default client + supplier and fill NULL links
python -m src.backfill_legacy_client_supplier_defaults
```

This command is idempotent: it reuses existing legacy records when present, updates only
`inventories.client_id IS NULL` and `aisles.client_supplier_id IS NULL`, prints before/after
counts, and does not modify pipeline prompts/providers/models, assets, or frontend flows.

## Tests

Create SQL Server test configuration (gitignored):

```bash
cp backend/.env.test.example backend/.env.test
```

Edit `backend/.env.test` and point `SQLSERVER_DATABASE` (or `SQLSERVER_CONNECTION_STRING`) at a **dedicated** database (name should clearly indicate test, e.g. `dinamic_inventory_test` or `dinamic-inventory-test`). Pytest loads `.env.test` **after** `.env` with override so your manual dev DB is not used.

Run tests from **repository root** (recommended; uses root `pytest.ini` and coverage):

```bash
pytest
```

Or from `backend/`:

```bash
cd backend && pytest
```

### SQL Server behaviour

- If SQL Server is configured but the database name is not clearly a test DB (and not on `DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST`), pytest **exits before collecting tests**. Escape hatch (exceptional): `DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER=1` (disables automatic integration cleanup too).
- `@pytest.mark.integration` tests that use SQL Server run **business-table cleanup before and after each test** when auto cleanup is enabled (see `backend/tests/conftest.py`). Disable with `DINAMIC_PYTEST_DISABLE_SQLSERVER_TEST_CLEANUP=1`.

### Manual local business-data cleanup (manual dev DB)

The cleanup script loads **`.env` + `backend/.env` only** — not `.env.test`. Use `--use-env-test` only if you deliberately want the same variables as pytest.

```bash
# Dry-run (counts only, no deletes)
python backend/scripts/clean_local_business_data.py

# Destructive delete (requires confirmation env + loopback SERVER= unless remote override)
DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1 python backend/scripts/clean_local_business_data.py --confirm
```

Deletes require `DINAMIC_CONFIRM_LOCAL_BUSINESS_DATA_DELETION=1`, `--confirm`, and a loopback `SERVER=` unless `DINAMIC_ALLOW_REMOTE_BUSINESS_DATA_CLEANUP=1`. After deletes, the script re-counts tables in the same transaction and aborts if critical business tables are non-empty.

Optional tuning: `DINAMIC_INVENTORY_JOBS_DELETE_MAX_ITERATIONS` (default `1000`) caps iterations when resolving `inventory_jobs` self-FK deletes.

## Local/dev worker verification

For the supplier reference-images flow, local/dev closure depends on the worker using the current backend code and local artifact paths without fake S3 requirements. Reference images are scoped to **client suppliers** (`supplier_reference_images`), not inventories.

### Expected local/dev behavior

- `ARTIFACT_STORAGE_PROVIDER=local` works without an S3 bucket.
- `python -m src.jobs.run_worker_dev` watches the backend directory and restarts the standard worker entrypoint on code changes.
- The standard worker still logs the active storage mode through `src.jobs.run_worker.main()`.
- A local run with supplier reference images should resolve artifacts from the local filesystem and persist the same `visual_reference_context` / execution-log traceability used in other environments (aisles must have `client_supplier_id` when references should attach).

### Smoke verification checklist

Run from the repository root:

```bash
# 1) Start the API and dev worker
uvicorn src.api.server:app --reload --port 8000
python -m src.jobs.run_worker_dev

# 2) Create client + supplier; upload supplier reference images (API or UI under Client detail)
# 3) Create an inventory (optional client link); create an aisle assigned to that supplier (client_supplier_id)
# 4) Upload aisle source assets and start aisle processing
```

Verify all of the following:

- worker log includes `Worker dev reloader watching .../backend`
- worker log includes `Worker artifact storage: provider=local`
- processing completes without requiring `artifact_s3_bucket`
- job execution log contains the Gemini request payload with `visual_reference_attachments`
- aisle status/list exposes `latest_job.reference_usage`
- replacing or deleting supplier reference images changes only future jobs, not historical `job.result_json`

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
- **DEV (OpenCloud):** migrations run automatically on the Ubuntu server during SSH deploy — see `docs/deployment/DEV-OPENCLOUD.md`. `check_deploy_secrets.sh` validates GCP key mounts before migrations; `dev_deploy_db_migrate.sh` runs `config-check` → `status` → conditional `apply` → `validate`. **Preflight without apply:** `DEV_DEPLOY_DB_MIGRATE_CHECK_ONLY=true bash scripts/dev_deploy_db_migrate.sh` (after `docker-compose up -d`). Place `secrets/gcp-service-account.json` at repo root or `backend/secrets/` with `docker-compose.override.yml` (example committed). Exit code **137** usually means OOM.
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
