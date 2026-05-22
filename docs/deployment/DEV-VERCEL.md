# DEV frontend — Vercel (Git integration only)

GitHub Actions **does not deploy** the frontend to Vercel. There is **no** Vercel workflow in `.github/workflows/`.

GitHub Actions only validates code quality (see **Develop quality gate** in [`.github/workflows/develop-quality-gate.yml`](../../.github/workflows/develop-quality-gate.yml): backend checks and frontend install, typecheck, lint, tests, build).

**Vercel** deploys the frontend through its **native GitHub integration** when commits are pushed or merged to **`develop`**.

## Vercel project settings (required)

**Project → Settings → Git**

| Setting | Value |
|---------|--------|
| Connected Git repository | This monorepo (`dinamic-gemini` or your org/repo name) |
| **Production Branch** | `develop` |
| **Root Directory** | `frontend` |

**Project → Settings → Build & Development Settings**

| Setting | Value |
|---------|--------|
| Framework Preset | Vite (or auto-detected) |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm install` or `npm ci` |

Do **not** set Root Directory to `frontend/frontend`. With Root Directory = `frontend`, Vercel builds from that folder only.

### GitHub App permissions

GitHub → **Settings → Applications → Installed GitHub Apps → Vercel**: this repository must be allowed.

### Ignored Build Step

**Settings → Git → Ignored Build Step** — if set, it can skip automatic builds. For normal DEV flow it should not block pushes to `develop` that touch `frontend/`.

Optional: **Wait for GitHub Actions** / required check **Develop quality gate** so Vercel does not build before CI passes.

## Deploy flow

```text
push or merge to develop
  → Develop quality gate (GitHub Actions): validation only
  → Vercel Git integration: Production deployment (automatic)
```

GitHub Actions must **never** run:

- `npx vercel pull` / `vercel pull`
- `npx vercel build` / `vercel build`
- `npx vercel deploy` / `vercel deploy`
- `--prebuilt`

The recurring error `frontend/frontend does not exist` came from Vercel CLI in Actions combined with Root Directory `frontend`. Removing CLI from Actions removes that failure mode.

## If no deployment appears in Vercel after push to develop

1. The commit is on **`develop`** (merged or pushed directly).
2. **Develop quality gate** succeeded on that commit (quality only; Vercel does not wait on Actions unless you configured it).
3. Vercel → **Deployments**: is there a build for that commit SHA?
4. **Settings → Git**: correct repo, Production Branch = `develop`, Root Directory = `frontend`.
5. **Ignored Build Step** is not blocking the commit.
6. Vercel GitHub App has access to this repository.
7. Push included changes under `frontend/` (or your Ignored Build Step still allows a build).

Manual redeploy: Vercel → **Deployments** → **Redeploy** on the target commit.

## If GitHub Actions still shows Vercel CLI in logs

That is an **old workflow run** (before `.github/workflows/deploy-dev-vercel-frontend.yml` was removed), or a **Re-run jobs** on an old commit. Do not use **Re-run** on those runs.

After the removal is merged to `develop`, validate locally:

```bash
grep -R "npx vercel" .github/workflows || true
grep -R "vercel deploy" .github/workflows || true
grep -R "vercel pull" .github/workflows || true
grep -R "vercel build" .github/workflows || true
```

All commands should print nothing.

## Legacy (archived, not used in CI)

CLI scripts that used to run from Actions: [`deployment/archive/vercel-cli-gha-legacy/`](../../deployment/archive/vercel-cli-gha-legacy/README.md).

## Related

- Backend DEV (OpenCloud): [`DEV-OPENCLOUD.md`](DEV-OPENCLOUD.md)
- Quality gate: [`../quality-gate.md`](../quality-gate.md)
