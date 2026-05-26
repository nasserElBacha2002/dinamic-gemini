# DEV — OpenCloud backend deploy (SSH + Docker Compose)

Automatic backend deploy runs from GitHub Actions (`.github/workflows/deploy-dev-opencloud-backend.yml`) after the develop quality gate, or via manual `workflow_dispatch`.

## Server flow

1. `git fetch` / reset to `origin/develop`
2. `cd backend` → `docker-compose down` → `build api` → `up -d`
3. `backend/scripts/dev_deploy_db_migrate.sh` (migrations inside the running API container)
4. Poll `http://127.0.0.1:${BACKEND_HOST_PORT}/health`

Environment for the API lives at the **repository root** `.env` (e.g. `/opt/dinamic/dinamic-gemini/.env`), loaded by `backend/docker-compose.yml`.

## Database migrations on deploy

`dev_deploy_db_migrate.sh` runs inside the API container after `docker-compose up -d`.

| Step | Command | On failure |
|------|---------|------------|
| Preflight | `db_migrate.py config-check` | Deploy stops |
| Status | `db_migrate.py status` | Deploy stops |
| Apply (if pending) | `db_migrate.py apply` | Deploy stops (only when `AUTO_APPLY_DEV_MIGRATIONS=true`, default) |
| Validate | `db_migrate.py validate` | Deploy stops |
| Final status | `db_migrate.py status` + clean check | Deploy stops |

### `doctor` is skipped by default

`db_migrate.py doctor` is a CLI alias for `config-check`. It is **not** run automatically during deploy to avoid redundant work and extra memory pressure on small DEV VMs.

Deploy logs include:

```text
Skipping migration doctor during deploy. Run it manually for deep diagnostics.
```

To run `doctor` during deploy anyway (not recommended on memory-constrained hosts):

```bash
export RUN_MIGRATION_DOCTOR_ON_DEPLOY=true
```

### Environment flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTO_APPLY_DEV_MIGRATIONS` | `true` | Apply pending migrations; if `false`, pending migrations fail the deploy |
| `RUN_MIGRATION_DOCTOR_ON_DEPLOY` | `false` | When `true`, run `doctor` after `config-check` (logs a memory warning) |

## Exit code 137 (process killed)

If a deploy step ends with **exit status 137**, the process was usually **SIGKILL**’d by the host — often **out-of-memory (OOM)** on small servers, not a missing SQL Server config.

Typical mitigations:

- Skip heavy steps during deploy (`doctor` is already skipped by default).
- Run deep checks manually when the server is idle.
- Increase VM memory or reduce concurrent containers.

## Manual migration commands (on the server)

From the repo:

```bash
cd /opt/dinamic/dinamic-gemini/backend

docker-compose exec api python3 scripts/db_migrate.py config-check
docker-compose exec api python3 scripts/db_migrate.py status
docker-compose exec api python3 scripts/db_migrate.py apply
docker-compose exec api python3 scripts/db_migrate.py validate
docker-compose exec api python3 scripts/db_migrate.py doctor
```

Or re-run the deploy migration script:

```bash
export AUTO_APPLY_DEV_MIGRATIONS=true
bash scripts/dev_deploy_db_migrate.sh
```

## Related

- Workflow: `.github/workflows/deploy-dev-opencloud-backend.yml`
- Migration script: `backend/scripts/dev_deploy_db_migrate.sh`
- Static checks: `backend/scripts/test_dev_deploy_db_migrate_static.sh`
