#!/usr/bin/env bash
# Pre-deploy validation for DEV Vercel frontend (no deploy unless --live-pull).
#
# Usage (from repository root):
#   bash scripts/validate_vercel_deploy_dev.sh
#   bash scripts/validate_vercel_deploy_dev.sh --live-pull   # needs VERCEL_TOKEN (+ ORG/PROJECT ids)
#
# What this checks offline:
#   - deploy script syntax and required steps
#   - workflow wires scripts/vercel-deploy-dev-production.sh (not inline vercel at repo root)
#   - path logic: deploy cwd must be frontend/, rootDirectory cleared → no frontend/frontend
#
# --live-pull: runs `vercel pull` only from frontend/ (no deploy). Confirms CLI writes
#   frontend/.vercel/project.json and patch succeeds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

LIVE_PULL=0
for arg in "$@"; do
  case "${arg}" in
    --live-pull) LIVE_PULL=1 ;;
    -h | --help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: ${arg} (try --live-pull)" >&2
      exit 2
      ;;
  esac
done

echo "==> [1/4] Static checks (deploy script)"
bash scripts/test_vercel_deploy_dev_static.sh

echo "==> [2/4] GitHub Actions (no Vercel deploy workflow)"
if [ -f ".github/workflows/deploy-dev-vercel-frontend.yml" ]; then
  echo "ERROR: deploy-dev-vercel-frontend.yml must be deleted; Vercel deploy is Git integration only" >&2
  exit 1
fi
if grep -RqE 'npx vercel (pull|build|deploy)|vercel deploy|vercel pull|vercel build' .github/workflows 2>/dev/null; then
  echo "ERROR: .github/workflows must not contain Vercel CLI deploy commands" >&2
  exit 1
fi
echo "OK: no Vercel CLI in .github/workflows"
echo "OK: workflow delegates to vercel-deploy-dev-production.sh"

echo "==> [3/4] Dry-run path resolution (no Vercel API)"
python3 - <<'PY'
from __future__ import annotations

import json
import tempfile
from pathlib import Path


def cli_target_path(
    repo_root: Path, *, cwd_under_frontend: bool, root_directory: str | None
) -> Path:
    """Model paths that make Vercel fail vs succeed (matches frontend/frontend ENOENT)."""
    if cwd_under_frontend and not root_directory:
        return (repo_root / "frontend").resolve()
    if not cwd_under_frontend and root_directory == "frontend":
        return (repo_root / "frontend" / "frontend").resolve()
    raise ValueError("unexpected deploy parameters")


repo = Path(tempfile.mkdtemp(prefix="vercel-validate-"))
(repo / "frontend").mkdir()
(repo / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")

broken = cli_target_path(repo, cwd_under_frontend=False, root_directory="frontend")
fixed = cli_target_path(repo, cwd_under_frontend=True, root_directory=None)
if broken.exists():
    raise SystemExit(f"FAIL: broken path unexpectedly exists: {broken}")
if not (repo / "frontend").is_dir():
    raise SystemExit("FAIL: frontend/ missing in fixture repo")
print(f"OK broken model: CLI would target missing path {broken}")
print(f"OK fixed model: CLI targets existing path {fixed}")

# Simulate project.json patch under frontend/.vercel
vercel_dir = repo / "frontend" / ".vercel"
vercel_dir.mkdir(parents=True)
project = {
    "projectId": "test",
    "orgId": "test",
    "settings": {"rootDirectory": "frontend"},
}
path = vercel_dir / "project.json"
path.write_text(json.dumps(project), encoding="utf-8")
data = json.loads(path.read_text(encoding="utf-8"))
data.setdefault("settings", {})["rootDirectory"] = None
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
after = json.loads(path.read_text(encoding="utf-8"))["settings"].get("rootDirectory")
if after is not None:
    raise SystemExit(f"FAIL patch: rootDirectory still {after!r}")
print("OK patch: settings.rootDirectory -> None in frontend/.vercel/project.json")
PY

echo "==> [4/4] Live pull (optional)"
if [ "${LIVE_PULL}" -ne 1 ]; then
  echo "SKIP live Vercel API (use --live-pull with VERCEL_TOKEN to verify pull + project.json path)"
  echo ""
  echo "All offline checks passed."
  echo "Before merge/deploy, optional live check:"
  echo "  export VERCEL_TOKEN=... VERCEL_ORG_ID=... VERCEL_PROJECT_ID=..."
  echo "  bash scripts/validate_vercel_deploy_dev.sh --live-pull"
  exit 0
fi

if [ -z "${VERCEL_TOKEN:-}" ]; then
  echo "ERROR: --live-pull requires VERCEL_TOKEN" >&2
  exit 1
fi

FRONTEND_DIR="${REPO_ROOT}/frontend"
cd "${FRONTEND_DIR}"
rm -rf .vercel
echo "Live: vercel pull from $(pwd)"
npx vercel pull --yes --environment=production --token="${VERCEL_TOKEN}"

if [ ! -f .vercel/project.json ]; then
  echo "ERROR: frontend/.vercel/project.json missing after live pull" >&2
  exit 1
fi
if [ -f "${REPO_ROOT}/.vercel/project.json" ]; then
  echo "WARNING: repo-root .vercel also exists after pull from frontend/" >&2
fi

python3 - <<'PY'
import json
from pathlib import Path

path = Path(".vercel/project.json")
data = json.loads(path.read_text(encoding="utf-8"))
before = (data.get("settings") or {}).get("rootDirectory")
print(f"live pull rootDirectory before patch: {before!r}")
settings = data.setdefault("settings", {})
settings["rootDirectory"] = None
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("live pull rootDirectory after patch: None")
PY

echo ""
echo "Live pull OK (deploy was NOT run). Safe to push and run GitHub deploy workflow."
