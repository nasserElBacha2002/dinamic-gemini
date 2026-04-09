# DEV deployment — OpenCloud (Ubuntu + Docker)

This document describes how **development** backend deployments work after moving off AWS ECS for DEV.

## Git branching (authoritative)

- Work happens on **feature branches**, merged into **`main`**.
- **`main` is not production.**
- Changes are merged **`main` → `develop`** when ready for the shared DEV environment.
- **Only `develop`** is deployed to the DEV server described here.
- **Production** will use a dedicated branch (e.g. `production`) later; that path is not defined in this repo yet.

Flow in short: **feature → main → develop → deploy**.

## What runs on push

GitHub Actions workflow: **`.github/workflows/deploy-dev-opencloud-backend.yml`**

- **Name:** `DEV — OpenCloud backend (SSH)`
- **Triggers:**
  - Push to **`develop`** when paths under **`backend/**`** change, or the workflow file itself changes.
  - **`workflow_dispatch`** (manual run).
- **Concurrency:** `dev-opencloud-backend-develop` — overlapping runs are queued (`cancel-in-progress: false`).
- **Not used:** AWS, ECS, ECR, IAM OIDC, migration ECS tasks.

### Jobs

1. **Migration file guard** — On `push` only, runs `backend/scripts/check_migration_presence.py` when a valid base SHA exists (same idea as the old ECS pipeline’s guard, without AWS).
2. **SSH deploy** — Connects on **SSH port 37783** (hardcoded in the workflow, not 22), hard-resets the repo to `origin/develop`, verifies repo path / compose file / root `.env` / `docker-compose` on `PATH`, then **`docker-compose down`** (best-effort), **`docker-compose up -d --build`**, and retries **local** `GET http://127.0.0.1:8000/health` for up to **~135s** (45 × 3s) so slow imports / startup after the container listens still pass.
3. **Optional public smoke** — If `DEV_BACKEND_URL` is set, curls `{BASE}/health` from the GitHub runner.

## Server layout

| Item | Value |
|------|--------|
| Repository path | `/opt/dinamic/dinamic-gemini` |
| Branch checked out | `develop` (hard reset to `origin/develop`) |
| Compose file | `backend/docker-compose.yml` |
| API port (host) | `8000` → container `8000` |
| Local artifact persistence (DEV, `ARTIFACT_STORAGE_PROVIDER=local`) | Bind mount **`data/output` → `/app/output`** (repo-relative from compose: `../data/output:/app/output`). With default **`OUTPUT_DIR=output`**, the effective artifact base remains **`/app/output/v3_uploads`** in the container; files survive **`docker-compose up --build`** and container recreate. On the canonical server path, host files live under **`/opt/dinamic/dinamic-gemini/data/output/`** (e.g. visual references under `…/data/output/v3_uploads/inventories/...`). The `data/` tree is gitignored. |
| Container env | **Repository root** `.env` at `/opt/dinamic/dinamic-gemini/.env` — referenced from compose as `../.env` (**not** in git) |
| SSH (Actions → server) | Port **37783** (set in workflow; change the workflow if your sshd port changes) |

### Non-interactive Git on the server

Automated deploy runs `git fetch origin` over SSH **without a TTY**. The clone at `/opt/dinamic/dinamic-gemini` must already be configured so **`git fetch` / `git pull` succeed without prompts**, for example:

- **SSH deploy key** with read access to the repo (`core.sshCommand` or `~/.ssh/config` host entry), or  
- **HTTPS** with a credential helper / long-lived token (not an interactive login).

If `git fetch` waits for a password, the workflow will hang or fail.

Remote commands (conceptually):

```bash
cd /opt/dinamic/dinamic-gemini
git fetch origin
git switch develop 2>/dev/null || git checkout develop
git reset --hard origin/develop
# Deploy script also checks: backend/docker-compose.yml exists, repo root .env exists, docker-compose on PATH
cd backend
docker-compose down --remove-orphans || true
docker-compose up -d --build
docker-compose ps
# Workflow retries GET /health on localhost for up to ~135s (45 x 3s).
```

## GitHub Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `DEV_HOST` | Yes | Server hostname or IP (no port — port **37783** is fixed in the workflow YAML) |
| `DEV_USER` | Yes | SSH user |
| `DEV_SSH_PRIVATE_KEY` | Yes | Private key for that user (PEM) |
| `DEV_BACKEND_URL` | No | e.g. `https://api-dev.example.com` — trailing slash optional; used for post-deploy `GET /health` from Actions |

No AWS secrets are used for this DEV path.

## One-time server setup

1. Clone the repo once (if not already):

   ```bash
   sudo mkdir -p /opt/dinamic
   sudo chown "$USER":"$USER" /opt/dinamic
   git clone <your-repo-url> /opt/dinamic/dinamic-gemini
   cd /opt/dinamic/dinamic-gemini
   git checkout develop
   ```

2. Ensure **`git fetch origin` works non-interactively** from that clone (see **Non-interactive Git on the server** above).

3. Create **`.env` at the repository root** (`/opt/dinamic/dinamic-gemini/.env`) with everything the API needs (SQL Server, keys, etc.). `backend/docker-compose.yml` loads it via `env_file: ../.env`. This file is gitignored.

### `.env` values with `$` (docker-compose v1)

**docker-compose** treats `$NAME` in many contexts as a variable to substitute. If a value must contain a **literal dollar** (e.g. passlib hashes like `$pbkdf2-sha256$...`, or other secrets with `$`), **double it**: use **`$$`** so compose passes a single `$` into the container (e.g. `$$pbkdf2-sha256$...`). Otherwise you will see warnings such as *The "pbkdf2" variable is not set* and values can be corrupted.

4. Install **Docker Engine** and the classic **`docker-compose`** standalone (on `PATH`). The Docker Compose **v2 plugin** (`docker compose`) is **not** required for this DEV flow.

5. Add the GitHub Actions (or deploy) **public SSH key** to `~/.ssh/authorized_keys` for `DEV_USER`.

6. First manual deploy (optional):

   ```bash
   cd /opt/dinamic/dinamic-gemini/backend
   docker-compose down --remove-orphans || true && docker-compose up -d --build
   ```

## Manual redeploy on the server

Same as the remote block above, or:

```bash
cd /opt/dinamic/dinamic-gemini && git fetch origin && git reset --hard origin/develop
cd backend && docker-compose down --remove-orphans || true && docker-compose up -d --build
```

## Database migrations (DEV) — **manual by design**

| Policy | Detail |
|--------|--------|
| **Deploy workflow** | Does **not** run `db_migrate.py` (no `apply`, no post-deploy validate). Keeps the SSH deploy simple, avoids blind applies against the shared DEV DB, and stays **AWS-free**. |
| **CI guard** | On **push** to `develop`, the **migration file guard** job still runs `check_migration_presence.py` when a valid base SHA exists, so DB-layer changes are not merged into `develop` without a migration file when required. |
| **Operators** | After a deploy, when schema changes are included in the new image, run migrations **on the server** explicitly (order: config-check → apply → validate). |

The old ECS DEV pipeline ran migrations inside a VPC task; OpenCloud DEV replaces that with **explicit operator steps** after deploy.

Example (service name `api` — see `backend/docker-compose.yml`):

```bash
cd /opt/dinamic/dinamic-gemini/backend
docker-compose run --rm api python scripts/db_migrate.py config-check
docker-compose run --rm api python scripts/db_migrate.py apply
docker-compose run --rm api python scripts/db_migrate.py validate
```

**Not intended:** wiring `apply` into GitHub Actions for this DEV path unless you add a separate, reviewed workflow later; the current design is **manual migrations on the VPS** after automated code deploy.

## SQL Server on DEV (OpenCloud)

- Full details: **`backend/README.md`** → *SQL Server configuration*.
- **`SQLSERVER_DRIVER`:** optional when an ODBC driver is auto-detected; otherwise set to the exact name from `pyodbc.drivers()` (typically **`ODBC Driver 18 for SQL Server`** in the shipped API/worker images). Host ODBC paths do not apply inside the container — use env loaded into the container only.
- **Schema guard skipped / incomplete SQL Server config** is expected until server, database, credentials, and a working driver (or full connection string) are configured.

## Frontend DEV

Point the frontend DEV build at this backend’s public URL (environment variable used by your frontend config). That is separate from this workflow.

## What happened to the old AWS DEV pipeline?

The following were **removed from active GitHub paths** so they no longer run:

- `.github/workflows/deploy-backend-dev.yml` — ECS/ECR API + worker + migration task deploy on `develop`.
- `.github/workflows/deploy-worker-dev.yml` — manual ECS schema validation.

**Preserved for reference** (future AWS production or migration):  
`deployment/archive/aws-ecs-dev-legacy/` — README, archived workflow YAML copies, and the ECS helper scripts (`ecs-register-task-and-deploy.sh`, `run-ecs-migration-task.sh`). Restore instructions are in that folder’s README.

**Not removed:** application code, `backend/scripts/db_migrate.py`, or `check_migration_presence.py` — still used by CI and operators.

## Worker container

The archived ECS workflow also built **`Dockerfile.worker`**. The minimal OpenCloud compose file deploys **only the API** (`backend/Dockerfile`). If you need the worker on the same host, extend `docker-compose.yml` with a second service or run the worker separately.
