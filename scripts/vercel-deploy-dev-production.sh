#!/usr/bin/env bash
# DEV Vercel deploy from GitHub Actions (remote build, production target).
#
# Vercel dashboard Root Directory is `frontend`. The CLI must not combine that with
# a second `frontend` segment (e.g. cwd under frontend/ or `vercel deploy frontend`).
#
# Strategy:
#   1. `vercel pull` at repository root (loads .vercel/project.json from Vercel).
#   2. Clear settings.rootDirectory in the local project.json for this CI deploy only.
#   3. `vercel deploy` from frontend/ (single path segment); .vercel is found via parent dir.
#
# Do not re-run casually from a subdirectory without reading this script.
set -euo pipefail

REPO_ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"

if [ "$(basename "${PWD}")" = "frontend" ]; then
  echo "ERROR: Vercel deploy must start from repository root, not frontend/" >&2
  exit 1
fi

if [ ! -d frontend ]; then
  echo "ERROR: frontend/ directory missing at ${REPO_ROOT}" >&2
  exit 1
fi

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "ERROR: VERCEL_TOKEN is not set" >&2
  exit 1
fi

echo "Repository root: ${REPO_ROOT}"
pwd
ls -la
echo "frontend/ preview:"
ls -la frontend | sed -n '1,40p'

echo "Removing stale .vercel link dirs..."
rm -rf .vercel frontend/.vercel

echo "==> vercel pull (production)"
npx vercel pull --yes --environment=production --token="${VERCEL_TOKEN}"

if [ ! -f .vercel/project.json ]; then
  echo "ERROR: .vercel/project.json missing after vercel pull" >&2
  exit 1
fi

if [ -d frontend/.vercel ]; then
  echo "ERROR: vercel pull created frontend/.vercel — expected link only at repo root" >&2
  exit 1
fi

echo "==> Adjust local project.json for CI (avoid frontend/frontend)"
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

echo "Deploying commit ${GITHUB_SHA:-unknown} from frontend/ (remote build, --prod)..."
cd frontend

if [ "$(basename "${PWD}")" != "frontend" ]; then
  echo "ERROR: expected cwd frontend/ before deploy" >&2
  exit 1
fi

# No path argument — do not run `vercel deploy frontend`.
npx vercel deploy --prod --yes --token="${VERCEL_TOKEN}"
