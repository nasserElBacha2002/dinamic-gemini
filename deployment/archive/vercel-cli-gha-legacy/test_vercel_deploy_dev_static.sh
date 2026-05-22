#!/usr/bin/env bash
# Static checks for scripts/vercel-deploy-dev-production.sh (no Vercel API calls).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/scripts/vercel-deploy-dev-production.sh"

bash -n "${TARGET}"

for needle in \
  'FRONTEND_DIR' \
  'cd "${FRONTEND_DIR}"' \
  'basename "${PWD}")" != "frontend"' \
  'rm -rf .vercel' \
  'vercel pull' \
  'rootDirectory' \
  '.vercel/project.json' \
  'vercel deploy --prod --yes'; do
  if ! grep -q "${needle}" "${TARGET}"; then
    echo "missing expected content: ${needle}" >&2
    exit 1
  fi
done

if grep -qE 'npx vercel (deploy|pull) frontend|--cwd frontend' "${TARGET}"; then
  echo "script must not pass frontend as vercel CLI path argument" >&2
  exit 1
fi

if grep -qE 'npx vercel build|vercel build --' "${TARGET}"; then
  echo "script must not run vercel build" >&2
  exit 1
fi

# Must not require pull only at repo root (CLI writes frontend/.vercel when root is frontend).
if grep -q 'expected link only at repo root' "${TARGET}"; then
  echo "script must not reject frontend/.vercel after pull" >&2
  exit 1
fi

echo "vercel-deploy-dev-production.sh static checks OK"
