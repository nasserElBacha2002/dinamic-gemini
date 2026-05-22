# DEV deploy — automatic DB migrations report

## Files changed

| File | Reason |
|------|--------|
| `backend/scripts/dev_deploy_db_migrate.sh` | DEV-only migration helper (exec in running `api` service) |
| `backend/scripts/test_dev_deploy_db_migrate_static.sh` | Static validation (bash -n + required steps) |
| `.github/workflows/deploy-dev-opencloud-backend.yml` | Wire helper after `up -d`; remove manual `run --rm` status/apply |
| `docs/deployment/DEV-OPENCLOUD.md` | DEV deploy + migration behavior documentation |
| `backend/README.md` | Point to automatic DEV migrations |

## Migration command sequence

Executed inside **`docker-compose exec -T api`** (same `.env` as API):

1. `config-check` — fail deploy on exit ≠ 0 (e.g. 3 = missing ODBC/DB config)
2. `doctor` — alias of config-check
3. `status` — log JSON; detect `pending_versions`
4. `apply` — **only if** `pending_versions` is non-empty and `AUTO_APPLY_DEV_MIGRATIONS` is true (default)
5. `validate` — fail deploy on exit 2 (schema incompatible)
6. `status` — fail deploy if `pending_versions` non-empty or `compatible` is false

**Note:** `validate` runs **after** apply, not before. Pre-apply `validate` would fail whenever the DB is behind code (pending migrations). That matches deploy safety goals.

## Conditional apply

- **Conditional:** `apply` runs only when initial `status` JSON has non-empty `pending_versions`.
- **Idempotent:** `run_pending_migrations` no-ops when nothing pending; script skips `apply` entirely when list is empty.
- **Toggle:** `AUTO_APPLY_DEV_MIGRATIONS=false` → warning + exit 1 if pending remain (no silent skip).

## Failure behavior

- Shell: `set -euo pipefail`; workflow SSH `script_stop: true`
- Any `db_migrate.py` non-zero exit fails the step
- Final `status` parsed in Python — fails if pending or incompatible after apply/validate
- Migration stdout/stderr not swallowed

## Production

- Only `.github/workflows/deploy-dev-opencloud-backend.yml` changed
- No production deploy workflow in repo
- Archived ECS DEV remains under `deployment/archive/aws-ecs-dev-legacy/` (unchanged)

## Manual validation

```bash
# On DEV server after deploy or locally with Compose up:
cd backend
docker-compose exec -T api python3 scripts/db_migrate.py status
docker-compose exec -T api python3 scripts/db_migrate.py validate

# Full DEV migration step (same as deploy):
AUTO_APPLY_DEV_MIGRATIONS=true bash scripts/dev_deploy_db_migrate.sh

# Static check (no Docker):
bash scripts/test_dev_deploy_db_migrate_static.sh
```

Scenarios to verify on DEV:

| Scenario | Expected |
|----------|----------|
| DB up to date | Deploy green; logs “No pending migrations; skipping apply” |
| Pending migration in repo | Deploy runs `apply`; final status clean |
| Broken migration SQL | `apply` or `validate` fails; deploy red |
| `AUTO_APPLY_DEV_MIGRATIONS=false` with pending | Deploy fails with warning |

## Risks / limitations

- Migrations require SQL Server reachable from the `api` container at deploy time (same as before).
- `docker-compose exec` needs the `api` container running; script waits up to ~90s.
- Health poll runs **after** migrations; brief window where API is up but schema still incompatible is reduced vs old order (apply before `up -d` used one-off `run --rm`).
- `doctor` duplicates `config-check` (intentional for log clarity).

## Tests

- `bash backend/scripts/test_dev_deploy_db_migrate_static.sh` — static checks only (no Docker in CI unless added to quality gate later).
