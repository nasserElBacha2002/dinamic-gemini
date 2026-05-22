# DEV Vercel — GitHub Actions workflow removed

## Decision

Remove **all** GitHub Actions involvement in Vercel frontend deploy. Vercel owns deploy via native Git integration on `develop`.

## Changes

| Item | Action |
|------|--------|
| `.github/workflows/deploy-dev-vercel-frontend.yml` | **Deleted** (was handoff-only; still registered as a workflow and confused with old CLI runs) |
| `docs/deployment/DEV-VERCEL.md` | Updated — no handoff workflow; quality gate + Vercel Git only |

**Kept (unchanged):**

- `.github/workflows/develop-quality-gate.yml` — validation only
- `.github/workflows/deploy-dev-opencloud-backend.yml` — backend SSH deploy only
- `.github/workflows/frontend-validate.yml` — optional path-filtered checks (not a deploy gate)

## Validation (run in repo root)

```bash
grep -R "npx vercel" .github/workflows || true
grep -R "vercel deploy" .github/workflows || true
grep -R "vercel pull" .github/workflows || true
grep -R "vercel build" .github/workflows || true
```

**Expected:** no output.

## Confirm after merge to `develop`

1. Push a small change under `frontend/` to `develop`.
2. GitHub Actions: only **Develop quality gate** (and optional **Frontend validate** / **DEV — OpenCloud backend** if paths match) — **no** workflow named `DEV — Vercel frontend` or `DEV — Vercel frontend handoff`.
3. Vercel → **Deployments**: new Production build for that commit SHA.

## Why logs still showed `npx vercel pull` / `npx vercel deploy`

- Workflow file on `develop` had not yet included the delete, **or**
- **Re-run jobs** on an older commit that still had CLI in YAML, **or**
- A run triggered from a branch/SHA before the migration.

After this delete is on `develop`, new pushes cannot start a Vercel CLI workflow from Actions.
