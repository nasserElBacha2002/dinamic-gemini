#!/usr/bin/env bash
# DEV Vercel deploy from GitHub Actions (remote build, production target).
#
# Vercel dashboard Root Directory is `frontend`. The CLI downloads project settings to
# frontend/.vercel/project.json when the app root is `frontend` — not repo-root/.vercel.
#
# Running pull or deploy from the repository root makes the CLI resolve frontend/frontend.
#
# Strategy (all steps under frontend/):
#   1. cd frontend/
#   2. vercel pull → writes ./.vercel/project.json
#   3. Clear settings.rootDirectory in that file (local CI only; dashboard unchanged)
#   4. vercel deploy --prod --yes (no path argument, no vercel build, no --prebuilt)
set -euo pipefail

REPO_ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FRONTEND_DIR="${REPO_ROOT}/frontend"

if [ ! -d "${FRONTEND_DIR}" ]; then
  echo "ERROR: frontend/ directory missing at ${REPO_ROOT}" >&2
  exit 1
fi

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "ERROR: VERCEL_TOKEN is not set" >&2
  exit 1
fi

echo "Repository root: ${REPO_ROOT}"
echo "Vercel app directory: ${FRONTEND_DIR}"
cd "${FRONTEND_DIR}"

if [ "$(basename "${PWD}")" != "frontend" ]; then
  echo "ERROR: expected cwd frontend/ before vercel commands, got: ${PWD}" >&2
  exit 1
fi

pwd
ls -la | sed -n '1,40p'

echo "Removing stale .vercel link dir under frontend/..."
rm -rf .vercel

echo "==> vercel pull (production) from frontend/"
npx vercel pull --yes --environment=production --token="${VERCEL_TOKEN}"

PROJECT_JSON=".vercel/project.json"
if [ ! -f "${PROJECT_JSON}" ]; then
  echo "ERROR: ${PROJECT_JSON} missing after vercel pull (expected under frontend/)" >&2
  exit 1
fi

echo "==> project.json location: ${PWD}/${PROJECT_JSON}"
if [ -f "${REPO_ROOT}/.vercel/project.json" ]; then
  echo "WARNING: unexpected repo-root .vercel — removing to avoid path confusion"
  rm -rf "${REPO_ROOT}/.vercel"
fi

echo "==> Adjust local project.json (avoid frontend/frontend on deploy)"
python3 - <<'PY'
import json
from pathlib import Path

path = Path(".vercel/project.json")
data = json.loads(path.read_text(encoding="utf-8"))
settings = data.setdefault("settings", {})
before = settings.get("rootDirectory")
settings["rootDirectory"] = None
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"settings.rootDirectory: {before!r} -> None (local CI only; dashboard unchanged)")
PY

echo "Deploying commit ${GITHUB_SHA:-unknown} (remote build, --prod)..."
# No path argument — never `vercel deploy frontend`.
npx vercel deploy --prod --yes --token="${VERCEL_TOKEN}"
