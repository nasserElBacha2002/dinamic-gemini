# Database Schema Deployment Guard (Generic Pattern)

## Objective

Prevent any deployment from reaching an environment when the target database schema is behind or incompatible with the application release.

## Architecture

- **Versioned migration files**
  - Location: `backend/src/database/migrations/versions/`
  - Naming: `<4-digit-version>_<short_description>.sql` (example: `0002_add_review_indexes.sql`)
- **Migration metadata table**
  - Table: `schema_migrations`
  - Tracks: `service_name`, `version`, `migration_name`, `checksum_sha256`, `deployment_id`, `applied_at`
- **Migration command**
  - `python backend/scripts/db_migrate.py status|apply|validate`
- **Runtime compatibility guard**
  - Startup check validates: `current_schema_version >= required_schema_version`
  - Readiness endpoint (`/ready`) returns `503` if incompatible
  - Health endpoint (`/health`) includes schema guard metadata
- **Concurrency safety**
  - Uses SQL Server `sp_getapplock` to serialize migration execution per service

## Deployment Order (Required)

1. Backup/snapshot and environment safety checks
2. Migration presence validation in CI (PR/merge gate)
3. Migration execution stage (`db_migrate.py apply`)
4. Compatibility validation stage (`db_migrate.py validate`)
5. Application deployment
6. Post-deploy smoke (`GET /ready`)

## CI/CD Enforcement Rules

- If DB-related backend code changes, a migration file must be present:
  - Script: `backend/scripts/check_migration_presence.py`
- Deploy must block if schema validation fails:
  - Command exits non-zero on incompatibility: `python scripts/db_migrate.py validate`
- Migration execution and app deployment are separated stages/jobs.
- Migration stage is idempotent and safe for retries.

## Rollback and Recovery

- **Migration fails before app deploy**
  - Stop deployment, investigate SQL error, fix migration, re-run pipeline.
- **App deploy succeeds but smoke fails**
  - Prefer forward-fix with immediate patch deploy.
  - If rollback is mandatory, roll back app image to last known compatible release only.
- **Destructive migration**
  - Must be phased: backward-compatible schema change first, code rollout second, cleanup migration later.
- **Backup expectation**
  - Production migration stage requires point-in-time restore capability (snapshot/backup policy managed by platform team).

## Environment Model

- Same pattern for `dev`, `staging`, `prod`.
- Environment-specific values come from CI/CD secrets/vars:
  - `SQLSERVER_CONNECTION_STRING`
  - `DB_SCHEMA_SERVICE_NAME`
  - `DB_SCHEMA_REQUIRED_VERSION` (optional)
  - `DEPLOYMENT_ID`

## Observability

- Startup logs include required/current versions and compatibility status.
- `/health` reports:
  - `schema_guard_checked`
  - `schema_compatible`
  - `required_schema_version`
  - `current_schema_version`
  - `schema_reason`
- `/ready` provides deployment-safe failure response with explicit reason.

## Developer Workflow

1. Add SQL migration file in `backend/src/database/migrations/versions/`.
2. Run locally:
   - `python backend/scripts/db_migrate.py apply`
   - `python backend/scripts/db_migrate.py validate`
3. Run tests and open PR.
4. CI enforces migration presence and schema compatibility.

## Operator Runbook (Concise)

1. Check migration status:
   - `python backend/scripts/db_migrate.py status`
2. Apply pending migrations:
   - `python backend/scripts/db_migrate.py apply`
3. Validate compatibility:
   - `python backend/scripts/db_migrate.py validate`
4. Confirm readiness:
   - `curl -f <base-url>/ready`
5. If failure:
   - Inspect logs for required/current versions
   - Stop rollout and apply forward-fix
