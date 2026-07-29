#!/usr/bin/env bash
# Phase 7 — migration 0073 preflight + apply/reapply notes (SQL Server).
# Requires SQL connection via repo .env / env settings. Does not auto-resolve duplicates.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${AUDIT_PYTHON:-$ROOT/backend/.venv/bin/python}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

echo "== Migration 0073 validation helper =="
echo "HEAD=$(git rev-parse HEAD)"

echo "--- preflight duplicates (exit non-zero if duplicates exist) ---"
set +e
"$PY" scripts/ops/preflight_0073_retry_of_duplicates.py
PF=$?
set -e
echo "preflight_exit=$PF"

echo "--- migration status (db_migrate) ---"
(cd backend && "$PY" scripts/db_migrate.py -- status) || true

echo "See backend/src/database/migrations/versions/0073_README.md for rollback/reapply."
echo "MIG_0073_HELPER_DONE"
