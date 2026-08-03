#!/usr/bin/env bash
# Local quality gate aligned with Main quality gate + frontend/mobile validate workflows.
# Exits non-zero on first failure. Does not use || true.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-backend/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "==> Backend: compileall"
( cd backend && "$PYTHON_BIN" -m compileall -q src )

echo "==> Backend: ruff"
( cd backend && "$PYTHON_BIN" -m ruff check . )

echo "==> Backend: mypy"
( cd backend && "$PYTHON_BIN" -m mypy src )

echo "==> Backend: pytest (repo root, same as CI)"
export PATH="$(cd backend && pwd)/.venv/bin:${PATH}"
pytest

echo "==> Frontend: npm ci (if node_modules missing)"
if [[ ! -d frontend/node_modules ]]; then
  ( cd frontend && npm ci )
fi

echo "==> Frontend: check:cache + typecheck + lint + test + build"
( cd frontend && npm run check:cache && npm run typecheck && npm run lint && npm run test -- --run && npm run build )

echo "==> Mobile: verify"
if [[ ! -d mobile/node_modules ]]; then
  ( cd mobile && npm ci )
fi
( cd mobile && npm run verify )

echo "==> Security: pip-audit"
( cd backend && "$PYTHON_BIN" -m pip install -q "setuptools>=83.0.0" pip-audit && pip-audit --skip-editable )

echo "==> Security: npm audit --audit-level=high (frontend)"
( cd frontend && npm audit --audit-level=high )

echo "==> Optional Android (set RUN_ANDROID=1 to enable)"
if [[ "${RUN_ANDROID:-0}" == "1" ]]; then
  ( cd mobile && npx expo prebuild -p android --non-interactive )
  ( cd mobile/android && ./gradlew :app:testDebugUnitTest :app:lintDebug assembleDebug --no-daemon )
fi

echo "Quality gate PASSED"
