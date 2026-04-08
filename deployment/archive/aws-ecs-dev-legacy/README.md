# Archived: AWS ECS / ECR DEV deployment (legacy)

These files are **not used** for current DEV deployment.

## Current DEV path

See [docs/deployment/DEV-OPENCLOUD.md](../../../docs/deployment/DEV-OPENCLOUD.md): GitHub Actions deploys `develop` to the Ubuntu/OpenCloud server over SSH with Docker Compose.

## What this archive is

Previously, pushes to `develop` (backend paths) triggered **`.github/workflows/deploy-backend-dev.yml`**, which:

- Built API and worker images, pushed to **ECR**
- Ran **one-off ECS tasks** for DB migrations
- Updated **ECS services** (API + worker) with digest-pinned task definitions

A second workflow, **`deploy-worker-dev.yml`**, offered manual **schema validation** via an ECS task (no full deploy).

Those workflows were **removed from `.github/workflows/`** so they no longer run automatically. Copies are kept here for reference if a **future production** pipeline on AWS reuses the same patterns.

## Files in this folder

| Path | Notes |
|------|--------|
| `workflows/deploy-backend-dev.yml` | Former auto DEV deploy on `develop` |
| `workflows/deploy-worker-dev.yml` | Former manual ECS schema validation |
| `scripts/ecs-register-task-and-deploy.sh` | Register task def + update ECS service |
| `scripts/run-ecs-migration-task.sh` | Run migration command in VPC via ECS |

## Restoring AWS automation

1. Copy `workflows/*.yml` from this folder into `.github/workflows/` (adjust names/triggers for **production** if desired).
2. Copy `scripts/*.sh` into `.github/scripts/` (workflows expect `../.github/scripts/…` from `backend/` job steps).
3. Configure GitHub **variables** and **AWS_ROLE_TO_ASSUME** as documented in the archived YAML headers.

Do **not** assume `main` is production; align triggers with your `production` branch when that exists.
