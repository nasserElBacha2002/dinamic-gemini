# DEV frontend — Vercel (Git integration)

The DEV frontend is deployed by **Vercel’s native GitHub integration**, not by Vercel CLI in GitHub Actions.

GitHub Actions only runs the **Develop quality gate** (build, test, lint, typecheck). See [`.github/workflows/develop-quality-gate.yml`](../../.github/workflows/develop-quality-gate.yml).

## Vercel project settings (required)

In the Vercel dashboard → **Project → Settings**:

| Setting | Value |
|---------|--------|
| **Git** → Connected repository | This monorepo |
| **Production Branch** | `develop` |
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm ci` (or default) |

Do **not** set Root Directory to `frontend/frontend`. With Root Directory = `frontend`, Vercel builds from that folder only.

## Deploy flow

```text
push to develop
  → Develop quality gate (GitHub Actions): frontend-quality job
  → Vercel Git integration: Production deployment for develop
```

GitHub Actions **does not** run:

- `npx vercel pull`
- `npx vercel build`
- `npx vercel deploy`
- `--prebuilt`

This avoids CLI path bugs (e.g. `frontend/frontend does not exist`).

## If no deployment appears after push

1. Confirm the push was to **`develop`** (not only `main`).
2. Vercel → **Deployments**: check for a new build for that commit.
3. Vercel → **Settings → Git**: repo connected, Production Branch = `develop`.
4. GitHub → **Develop quality gate**: must succeed (Vercel may wait for required checks if configured).
5. Confirm changes are under `frontend/` (Vercel still builds the whole app root `frontend`, not individual files only).

## Manual redeploy

Use Vercel dashboard → **Deployments** → **Redeploy** on the target commit, or push an empty commit to `develop` after the quality gate passes.

Optional: **Deploy Hooks** (Settings → Git → Deploy Hooks) if you need to trigger a build from a script without the CLI. Store the hook URL as a GitHub secret and `curl -X POST` it from a custom workflow.

## Legacy: Vercel CLI from Actions (removed)

Former workflow: `.github/workflows/deploy-dev-vercel-frontend.yml` (removed).

Archived scripts (do not use in CI): [`deployment/archive/vercel-cli-gha-legacy/`](../../deployment/archive/vercel-cli-gha-legacy/README.md).

## Related

- Backend DEV (OpenCloud): [`DEV-OPENCLOUD.md`](DEV-OPENCLOUD.md)
- Quality gate: [`../quality-gate.md`](../quality-gate.md)
