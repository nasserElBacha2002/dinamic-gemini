# DEV deploy — OpenCloud (SSH + Docker Compose)

Automatic deploy for the **develop** branch: GitHub Actions workflow [`.github/workflows/deploy-dev-opencloud-backend.yml`](../../.github/workflows/deploy-dev-opencloud-backend.yml).

**Production:** not configured in this repo. `main` is not production. Only DEV OpenCloud is automated here.

## Server layout

| Item | Path |
|------|------|
| Repository | `/opt/dinamic/dinamic-gemini` |
| Compose file | `backend/docker-compose.yml` |
| Secrets / DB env | Repository root `.env` (loaded by Compose `env_file: ../.env`) |
| Default API host port | `8001` → container `8000` (override with `BACKEND_HOST_PORT` on the server) |

Deploy uses **`docker-compose`** (v1 standalone) on the server, not `docker compose` v2.

## Deploy flow (backend)

After **Develop quality gate** succeeds on a push to `develop` (with `backend/**` changes):

1. SSH to DEV host, `git reset --hard origin/develop`
2. Patch Compose host port (`backend/scripts/patch_compose_host_port.py`)
3. `docker-compose down`, `docker-compose build api`, `docker-compose up -d`
4. **Automatic DB migrations** — `backend/scripts/dev_deploy_db_migrate.sh`
5. Poll `http://127.0.0.1:${BACKEND_HOST_PORT}/health` on the server

Frontend DEV: [`.github/workflows/deploy-dev-vercel-frontend.yml`](../../.github/workflows/deploy-dev-vercel-frontend.yml).

## Automatic database migrations (DEV)

Migrations run **inside the running `api` container** so they use the same image and `.env` as the API (`docker-compose exec -T api`).

Helper script: **`backend/scripts/dev_deploy_db_migrate.sh`**

### Command sequence

| Step | CLI | On failure |
|------|-----|------------|
| 1 | `config-check` | Deploy exits non-zero (exit 3 if DB config missing) |
| 2 | `doctor` | Same as config-check (alias) |
| 3 | `status` | Deploy exits if config/DB unreachable |
| 4 | `apply` | **Only if** `pending_versions` is non-empty; skipped when already up to date |
| 5 | `validate` | Deploy exits non-zero (exit 2 if schema incompatible) |
| 6 | `status` | Deploy exits if `pending_versions` non-empty or `compatible` is false |

`apply` is idempotent: when there are no pending migrations, the CLI applies nothing and the script skips the apply step.

### Toggle: disable automatic apply

```bash
export AUTO_APPLY_DEV_MIGRATIONS=false
```

Default: **`true`** (unset).

When `false` and pending migrations exist, deploy **fails** after printing a warning (migrations are not left silently unapplied).

### Manual inspection (on the server)

```bash
cd /opt/dinamic/dinamic-gemini/backend
docker-compose exec -T api python3 scripts/db_migrate.py status
docker-compose exec -T api python3 scripts/db_migrate.py validate
docker-compose exec -T api python3 scripts/db_migrate.py config-check
```

Apply manually only when needed (e.g. toggle was false or a failed deploy):

```bash
docker-compose exec -T api python3 scripts/db_migrate.py apply
docker-compose exec -T api python3 scripts/db_migrate.py status
```

### When migration checks fail

- Deploy job **stops** (`set -euo pipefail`, `script_stop: true` on SSH action).
- Migration JSON is printed to the deploy log (not hidden).
- API may be running from `up -d` but schema may be behind code — fix migrations and re-run deploy or apply manually.

## Archived AWS ECS DEV

Former ECS-based DEV automation (including a migration task) lives under [`deployment/archive/aws-ecs-dev-legacy/`](../../deployment/archive/aws-ecs-dev-legacy/README.md). It is **not** used by current OpenCloud deploy.

## Related docs

- Schema migrations CLI: [`backend/README.md`](../../backend/README.md) — *Schema Migrations and Deployment Guard*
- Quality gate before deploy: [`docs/quality-gate.md`](../quality-gate.md)
