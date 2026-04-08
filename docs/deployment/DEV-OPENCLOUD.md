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
2. **SSH deploy** — Connects to the server, hard-resets the repo to `origin/develop`, builds and starts Docker Compose for the API.
3. **Optional public smoke** — If `DEV_BACKEND_URL` is set, curls `{BASE}/health` from the GitHub runner.

## Server layout

| Item | Value |
|------|--------|
| Repository path | `/opt/dinamic/dinamic-gemini` |
| Branch checked out | `develop` (hard reset to `origin/develop`) |
| Compose file | `backend/docker-compose.yml` |
| API port (host) | `8000` |
| Container env | `backend/.env` on the server (**not** in git) |

Remote commands (conceptually):

```bash
cd /opt/dinamic/dinamic-gemini
git fetch origin
git switch develop 2>/dev/null || git checkout develop
git reset --hard origin/develop
cd backend
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
curl -sfS http://127.0.0.1:8000/health
```

## GitHub Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `DEV_HOST` | Yes | Server hostname or IP |
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

2. Ensure **`git fetch` works** (deploy key or HTTPS credentials on the server).

3. Create **`backend/.env`** with everything the API needs (SQL Server, keys, etc.). This file is gitignored.

4. Install **Docker Engine** + **Docker Compose v2** plugin.

5. Add the GitHub Actions (or deploy) **public SSH key** to `~/.ssh/authorized_keys` for `DEV_USER`.

6. First manual deploy (optional):

   ```bash
   cd /opt/dinamic/dinamic-gemini/backend
   docker compose build --pull && docker compose up -d
   ```

## Manual redeploy on the server

Same as the remote block above, or:

```bash
cd /opt/dinamic/dinamic-gemini && git fetch origin && git reset --hard origin/develop
cd backend && docker compose build --pull && docker compose up -d --remove-orphans
```

## Database migrations (DEV)

The OpenCloud workflow **does not** run `db_migrate.py` automatically. The old ECS pipeline ran migrations inside a VPC task; on the VPS you should run migrations when schema changes land, for example:

```bash
cd /opt/dinamic/dinamic-gemini/backend
# adjust: run via compose exec, or a one-off container with same .env
docker compose run --rm api python scripts/db_migrate.py config-check
docker compose run --rm api python scripts/db_migrate.py apply
docker compose run --rm api python scripts/db_migrate.py validate
```

(Exact invocation depends on how you mount env and whether the API service name is `api` — see `backend/docker-compose.yml`.)

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
