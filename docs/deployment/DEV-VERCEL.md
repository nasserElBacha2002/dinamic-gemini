# DEV frontend — Vercel (Git integration)

GitHub Actions **does not deploy** the frontend. Vercel is the **source of truth** for DEV frontend deployments via its **native GitHub integration** when commits land on `develop`.

The **Develop quality gate** still validates the frontend in Actions (build, test, lint, typecheck). See [`.github/workflows/develop-quality-gate.yml`](../../.github/workflows/develop-quality-gate.yml).

After a successful push to `develop`, the workflow [**DEV — Vercel frontend handoff**](../../.github/workflows/deploy-dev-vercel-frontend.yml) only logs a reminder. It does **not** call Vercel CLI and does **not** trigger a Vercel build.

## Vercel project settings (required)

In the Vercel dashboard → **Project → Settings**:

| Setting | Value |
|---------|--------|
| **Git** → Connected repository | This monorepo (correct GitHub org/repo) |
| **Production Branch** | `develop` |
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm ci` (or default) |

Do **not** set Root Directory to `frontend/frontend`. With Root Directory = `frontend`, Vercel builds from that folder only.

### GitHub App permissions

Under **Settings → Git** (or GitHub → Installed GitHub Apps → Vercel):

- Vercel must have access to this repository.
- If the repo was recently added to the org, confirm Vercel is allowed on that repo.

### Ignored Build Step

If **Settings → Git → Ignored Build Step** is set, a matching command can skip automatic builds. For normal DEV flow it should be empty or not block `develop` pushes with `frontend/` changes.

Optional: enable **Wait for GitHub Actions** / required check **Develop quality gate** so Vercel does not build before CI passes.

## Deploy flow

```text
push to develop
  → Develop quality gate (GitHub Actions): frontend-quality job
  → Vercel Git integration: Production deployment (automatic)
  → DEV — Vercel frontend handoff (GitHub Actions): notice only, no CLI
```

GitHub Actions **never** runs:

- `npx vercel pull`
- `npx vercel build`
- `npx vercel deploy`
- `--prebuilt`

Legacy CLI deploys caused `frontend/frontend does not exist`; that path is removed from CI.

## If no deployment appears in Vercel after push to develop

1. Push was to **`develop`** (not only `main`).
2. **Develop quality gate** succeeded on that commit.
3. Vercel → **Deployments**: new build for that commit SHA?
4. Vercel → **Settings → Git**: connected repo, Production Branch = `develop`, Root Directory = `frontend`.
5. **Ignored Build Step** not blocking the commit.
6. GitHub App / Vercel installation has permission on this repo.
7. Changes include files under `frontend/` (or a full rebuild is still expected for any `develop` push if not ignored).

Manual redeploy: Vercel → **Deployments** → **Redeploy** on the target commit.

## GitHub workflow handoff (not a deploy)

Workflow name: **DEV — Vercel frontend handoff**

- Runs after **Develop quality gate** on successful **push** to **develop** only.
- **`workflow_dispatch`**: informational reminder; does not deploy.
- Does **not** re-run old jobs that used Vercel CLI.

If Actions logs show `npx vercel pull`, `Deploying commit … to Vercel (production, remote build)…`, or `frontend/frontend`, that is an **old workflow run** (Re-run on a commit before the Git-integration migration). Do not use **Re-run jobs** on those runs.

## Optional: Deploy Hook (no CLI)

**Settings → Git → Deploy Hooks** — trigger a build with `curl -X POST` to the hook URL without using Vercel CLI in Actions.

## Legacy: Vercel CLI from Actions (removed)

Archived scripts (do not use in CI): [`deployment/archive/vercel-cli-gha-legacy/`](../../deployment/archive/vercel-cli-gha-legacy/README.md).

## Related

- Backend DEV (OpenCloud): [`DEV-OPENCLOUD.md`](DEV-OPENCLOUD.md)
- Quality gate: [`../quality-gate.md`](../quality-gate.md)
