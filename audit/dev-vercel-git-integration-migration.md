# DEV frontend — migration to Vercel Git integration

## Decision

**Option A (final):** No Vercel-related GitHub Actions workflow. Vercel deploys automatically when `develop` receives commits (native Git integration).

## Changes

| Item | Action |
|------|--------|
| `.github/workflows/deploy-dev-vercel-frontend.yml` | **Deleted** — no handoff, no CLI |
| `docs/deployment/DEV-VERCEL.md` | Documents Git-only deploy and Vercel dashboard checklist |
| `deployment/archive/vercel-cli-gha-legacy/` | Archived CLI scripts (not used in CI) |
| `develop-quality-gate.yml` | Comments: frontend validated in Actions; deploy on Vercel |
| `docs/deployment/DEV-OPENCLOUD.md` | Link to DEV-VERCEL |

See also: [`dev-vercel-actions-workflow-removed.md`](dev-vercel-actions-workflow-removed.md).

## GitHub Actions behavior

- **Develop quality gate** runs `frontend-quality` (npm ci, check:cache, typecheck, lint, test, build).
- **No** workflow runs `npx vercel pull`, `vercel build`, or `vercel deploy`.
- Error `frontend/frontend does not exist` **cannot** occur from Actions (no Vercel workflow).

## Vercel dashboard checklist

- [ ] Git repository connected
- [ ] Production Branch = `develop`
- [ ] Root Directory = `frontend`
- [ ] Build Command = `npm run build`
- [ ] Output Directory = `dist`

## Verify after merge

1. `grep -R "npx vercel" .github/workflows` → empty
2. Push to `develop` with a small `frontend/` change
3. GitHub: **Develop quality gate** succeeds; no Vercel-named workflow
4. Vercel: new **Production** deployment for that commit SHA

## Optional: gate before Vercel build

Vercel → Settings → Git → **Wait for GitHub Actions** / required check **Develop quality gate**.
