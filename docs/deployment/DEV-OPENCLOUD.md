# DEV — OpenCloud backend deploy (SSH + Docker Compose)

Automatic backend deploy runs from GitHub Actions (`.github/workflows/deploy-dev-opencloud-backend.yml`) after the develop quality gate, or via manual `workflow_dispatch`.

## Server flow

1. `git fetch` / reset to `origin/develop`
2. `cd backend` → GCP secrets preflight (host) → `docker-compose down` → `build api` → `up -d`
3. GCP secrets preflight (container) → `dev_deploy_db_migrate.sh`
4. Poll `http://127.0.0.1:${BACKEND_HOST_PORT}/health`

Environment for the API lives at the **repository root** `.env` (e.g. `/opt/dinamic/dinamic-gemini/.env`), loaded by `backend/docker-compose.yml`.

## GCP credentials (`GOOGLE_APPLICATION_CREDENTIALS`)

When using GCS artifact storage, `.env` should include:

```env
ARTIFACT_STORAGE_PROVIDER=gcs
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-service-account.json
```

The JSON key must exist on the **host** and be visible inside the **api** container at that path. Deploy fails early with an actionable error if not.

### Supported host layouts (pick one)

| Host file | Compose mount |
|-----------|----------------|
| `secrets/gcp-service-account.json` (repo root) | Default in `backend/docker-compose.yml`: `../secrets:/app/secrets:ro` |
| `backend/secrets/gcp-service-account.json` | Server-local `backend/docker-compose.override.yml` (from `docker-compose.override.example.yml`): `./secrets:/app/secrets:ro` |

**Never commit** `gcp-service-account.json`. Override files are gitignored.

### Server setup (one-time)

```bash
cd /opt/dinamic/dinamic-gemini

# Option A — repo root (default compose mount)
mkdir -p secrets
# copy your key to secrets/gcp-service-account.json

# Option B — under backend/ (override mount)
mkdir -p backend/secrets
# copy your key to backend/secrets/gcp-service-account.json
cp backend/docker-compose.override.example.yml backend/docker-compose.override.yml
```

Deploy can auto-create `docker-compose.override.yml` from the example when `backend/secrets/gcp-service-account.json` exists and override is missing.

### Manual verification

```bash
cd /opt/dinamic/dinamic-gemini/backend

ls -la secrets/gcp-service-account.json
ls -la ../secrets/gcp-service-account.json

docker-compose exec api ls -la /app/secrets/gcp-service-account.json
docker-compose exec api test -f /app/secrets/gcp-service-account.json

bash scripts/check_deploy_secrets.sh host
bash scripts/check_deploy_secrets.sh container
docker-compose exec api python3 scripts/db_migrate.py status
```

### Pydantic error vs deploy preflight

If migrations fail with:

```text
google_application_credentials must point to an existing file
got '/app/secrets/gcp-service-account.json'
```

the file is missing **inside the container** (mount or host path wrong). Fix the mount, not AppSettings validation.

## Database migrations on deploy

`dev_deploy_db_migrate.sh` runs inside the API container after `docker-compose up -d`.

| Step | Command | On failure |
|------|---------|------------|
| Secrets | `check_deploy_secrets.sh container` | Deploy stops |
| Preflight | `db_migrate.py config-check` | Deploy stops |
| Status | `db_migrate.py status` | Deploy stops |
| Apply (if pending) | `db_migrate.py apply` | Deploy stops (only when `AUTO_APPLY_DEV_MIGRATIONS=true`, default) |
| Validate | `db_migrate.py validate` | Deploy stops |
| Final status | `db_migrate.py status` + clean check | Deploy stops |

### `doctor` is skipped by default

`db_migrate.py doctor` is a CLI alias for `config-check`. It is **not** run automatically during deploy.

To run `doctor` during deploy anyway:

```bash
export RUN_MIGRATION_DOCTOR_ON_DEPLOY=true
```

### Environment flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTO_APPLY_DEV_MIGRATIONS` | `true` | Apply pending migrations; if `false`, pending migrations fail the deploy |
| `RUN_MIGRATION_DOCTOR_ON_DEPLOY` | `false` | When `true`, run `doctor` after `config-check` |

## Exit code 137 (process killed)

If a deploy step ends with **exit status 137**, the process was usually **SIGKILL**’d by the host — often **out-of-memory (OOM)** on small servers.

## Related

- Workflow: `.github/workflows/deploy-dev-opencloud-backend.yml`
- Secrets check: `backend/scripts/check_deploy_secrets.sh`
- Migration script: `backend/scripts/dev_deploy_db_migrate.sh`
- Override example: `backend/docker-compose.override.example.yml`
- Repo secrets doc: `secrets/README.md`
