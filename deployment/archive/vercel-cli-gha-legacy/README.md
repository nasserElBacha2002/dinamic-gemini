# Archived — Vercel CLI deploy from GitHub Actions

**Status:** Removed from CI (Option A: Vercel native Git integration).

These scripts were used when `.github/workflows/deploy-dev-vercel-frontend.yml` ran `npx vercel pull` / `npx vercel deploy` from Actions. That workflow file has been **deleted**; Vercel deploy is Git integration only. Do not restore CLI deploy in `.github/workflows/`.

**Current DEV frontend deploy:** see [`docs/deployment/DEV-VERCEL.md`](../../../docs/deployment/DEV-VERCEL.md).

| File | Purpose (historical) |
|------|----------------------|
| `vercel-deploy-dev-production.sh` | pull + patch rootDirectory + deploy from `frontend/` |
| `validate_vercel_deploy_dev.sh` | Pre-deploy offline/live-pull checks |
| `test_vercel_deploy_dev_static.sh` | Static grep/bash checks |

Do not run `vercel-deploy-dev-production.sh` in CI unless restoring the legacy workflow intentionally.
