# DEV frontend — migration to Vercel Git integration

## Decision

**Option A:** Remove Vercel CLI from GitHub Actions. Vercel deploys automatically when `develop` receives commits (native Git integration).

## Changes

| Item | Action |
|------|--------|
| `.github/workflows/deploy-dev-vercel-frontend.yml` | **Removed** |
| `docs/deployment/DEV-VERCEL.md` | **Added** — Vercel settings and troubleshooting |
| `deployment/archive/vercel-cli-gha-legacy/` | Archived CLI scripts (not used in CI) |
| `develop-quality-gate.yml` | Comments updated |
| `docs/deployment/DEV-OPENCLOUD.md` | Link to DEV-VERCEL |

## GitHub Actions behavior

- **Develop quality gate** still runs `frontend-quality` (npm ci, check:cache, typecheck, lint, test, build).
- **No** `npx vercel pull`, `vercel build`, or `vercel deploy` in any workflow.
- Error `frontend/frontend does not exist` **cannot** occur from Actions (CLI not invoked).

## Vercel dashboard checklist

- [ ] Git repository connected
- [ ] Production Branch = `develop`
- [ ] Root Directory = `frontend`
- [ ] Build Command = `npm run build`
- [ ] Output Directory = `dist`

## Verify after merge

1. Push to `develop` with a small `frontend/` change.
2. GitHub: **Develop quality gate** succeeds.
3. Vercel: new **Production** deployment for that commit SHA.
4. DEV URL shows the change.

## Optional: gate before Vercel build

In Vercel → Settings → Git → enable **Wait for GitHub Actions** / required check **Develop quality gate** so Vercel does not build before CI passes.

## Option B (not implemented)

Deploy Hook + `curl` from Actions — use if you need Actions to *trigger* deploy without CLI. Documented in `DEV-VERCEL.md`.
