# DEV Vercel deploy — path filter fix

## Symptom

After a successful **Develop quality gate** on push to `develop`, the workflow **DEV — Vercel frontend** skipped deploy with:

```text
No frontend or this workflow changes; skipping deploy.
```

even when `git diff` listed `frontend/**` and `.github/workflows/deploy-dev-vercel-frontend.yml`.

Logs sometimes showed:

```text
echo: write error: Broken pipe
```

The Vercel build job could still pass in the quality gate, but **`deploy` job** never ran (`deploy=false`), so no new deployment appeared in Vercel.

## Root cause

`should-deploy` used:

```bash
if echo "${CHANGED}" | grep -qE '^frontend/|...'; then
```

With **`set -euo pipefail`**:

- `grep -q` exits as soon as it finds a match and closes the read end of the pipe.
- `echo` may receive **SIGPIPE** while writing the rest of the file list.
- With **pipefail**, the pipeline’s exit status is non-zero, so the **`if` branch is false** even when matches exist.

Result: **`deploy=false`** incorrectly.

## Fix

Use a **here-string** (or file) so `grep` is not paired with `echo` on a pipe:

```bash
if grep -qE "${FRONTEND_PATH_RE}" <<< "${CHANGED}"; then
  ...
fi
```

Matching paths for logs use `grep -E ... <<< "${CHANGED}"` (no `-q`), with `|| true` where needed.

## Files changed

| File | Change |
|------|--------|
| `.github/workflows/deploy-dev-vercel-frontend.yml` | Pipefail-safe path detection + clearer logs |
| `.github/workflows/deploy-dev-opencloud-backend.yml` | Same pattern for backend path filter (prevent identical bug) |

## Behavior preserved

- Deploy only after quality gate **success** on **push** to **develop**.
- Deploy when `frontend/**` or this workflow file changed.
- Skip when only backend (or unrelated) paths changed.
- **`workflow_dispatch`** still forces `deploy=true`.

## How to verify

1. Push to `develop` with a change under `frontend/` (after quality gate succeeds).
2. In **DEV — Vercel frontend** → job **Gate — after quality gate**:
   - Log must **not** contain `Broken pipe`.
   - Log must show `Frontend-relevant changes detected; deploy=true`.
3. Job **Vercel pull + build + deploy** must run (not skipped).
4. Vercel dashboard shows a new deployment for the commit SHA.

**Immediate unblock:** run **workflow_dispatch** on **DEV — Vercel frontend** for the commit that was skipped.

## Follow-up: `spawn sh ENOENT` on local `vercel build`

### Symptom

Deploy job ran but failed at:

```text
npx vercel build --token="${VERCEL_TOKEN}"
Error: spawn sh ENOENT
```

### Cause

The workflow ran **`vercel build` locally** in GitHub Actions, then **`vercel deploy --prebuilt`**. Local build requires a full shell toolchain; the runner step failed when the CLI could not spawn `sh`.

### Fix (2026-05-22)

Removed local build and prebuilt deploy. Vercel builds on its own infrastructure:

```bash
npx vercel pull --yes --environment=production --token="${VERCEL_TOKEN}"
npx vercel deploy --prod --yes --token="${VERCEL_TOKEN}"
```

- No `vercel build` in Actions.
- No `--prebuilt`.
- **`--prod`** kept for DEV (develop → Production in Vercel dashboard).
- Removed redundant `npm ci` on the runner (install happens on Vercel during remote build).

## Follow-up: `frontend/frontend` path does not exist

### Symptom

```text
The provided path ".../frontend/frontend" does not exist.
```

### Cause

Vercel project **Root Directory** is `frontend`, but the workflow ran `vercel pull` / `vercel deploy` with `working-directory: frontend`, so the CLI resolved `frontend` + `frontend`.

### Fix

Removed job-level `working-directory: frontend` from the deploy job. Vercel steps run from the **repository root**; Vercel applies its configured Root Directory `frontend`.

## Manual validation (local shell)

Simulate the old bug vs fix:

```bash
CHANGED=$'frontend/src/App.tsx\n.github/workflows/deploy-dev-vercel-frontend.yml'
set -o pipefail
# Broken (may fail):
# echo "${CHANGED}" | grep -qE '^frontend/' && echo match || echo no-match
# Fixed:
grep -qE '^frontend/' <<< "${CHANGED}" && echo match || echo no-match
```
