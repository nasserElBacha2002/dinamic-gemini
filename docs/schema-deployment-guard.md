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
- **Migration execution model (production)**
  - GitHub Actions **does not connect to SQL Server directly**.
  - Runner calls ECS API only, then runs one-off task in VPC:
    - `python scripts/db_migrate.py config-check`
    - `python scripts/db_migrate.py apply`
    - `python scripts/db_migrate.py validate`
  - Script used by workflows: `.github/scripts/run-ecs-migration-task.sh`
  - Task definition must use CloudWatch logs (`awslogs`) with configured `awslogs-group` and `awslogs-stream-prefix` for traceability.
- **Runtime compatibility guard**
  - Startup check validates: `current_schema_version >= required_schema_version`
  - Readiness endpoint (`/ready`) returns `503` if incompatible
  - Health endpoint (`/health`) includes schema guard metadata
- **Concurrency safety**
  - Uses SQL Server `sp_getapplock` to serialize migration execution per service

## Deployment Order (Required)

1. Backup/snapshot and environment safety checks
2. CI schema guard (migration presence by diff)
3. Build/push backend image to ECR
4. Run one-off ECS migration task in VPC (`config-check && apply && validate`)
5. Deploy ECS service(s) only if migration task exits `0`
6. Post-deploy smoke (`GET /ready`)

## CI/CD Enforcement Rules

- If DB-related backend code changes, a migration file must be present:
  - Script: `backend/scripts/check_migration_presence.py`
- Deploy blocks if ECS migration task fails (run-task failure, stop reason, or non-zero container exit code).
- Migration execution and app deployment are separated phases.
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
- CI runner env requires only AWS/ECS metadata:
  - `MIGRATION_TASK_DEFINITION`
  - `MIGRATION_CONTAINER_NAME`
  - `MIGRATION_SUBNETS`
  - `MIGRATION_SECURITY_GROUPS`
  - optional `MIGRATION_ASSIGN_PUBLIC_IP` / `MIGRATION_LAUNCH_TYPE` / `MIGRATION_PLATFORM_VERSION`
- SQL Server credentials/config remain inside ECS task definition (env/secrets) in AWS.

### Common failures

| Symptom | Fix |
|--------|-----|
| ECS `run-task` failure before start | Check task definition, IAM role permissions, subnet/SG settings. |
| Container exit non-zero in migration task | Check CloudWatch logs for `python scripts/db_migrate.py ...` output and DB schema/config errors. |
| Task cannot reach DB | Validate VPC routing, SG egress/ingress between task and RDS. |

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
   - `python backend/scripts/db_migrate.py config-check`
   - `python backend/scripts/db_migrate.py apply`
   - `python backend/scripts/db_migrate.py validate`
3. Run tests and open PR.
4. CI enforces migration presence and runs ECS migration task before deploy.

## Operator Runbook (Concise)

1. Trigger deploy pipeline.
2. Inspect ECS migration task output in workflow logs:
   - task arn
   - stopped reason
   - migration container exit code
3. If migration task failed:
   - inspect CloudWatch stream hint printed by script
   - fix config/schema SQL and rerun
4. Confirm readiness:
   - `curl -f <base-url>/ready`
5. If smoke fails:
   - inspect logs for required/current versions
   - stop rollout and apply forward-fix
