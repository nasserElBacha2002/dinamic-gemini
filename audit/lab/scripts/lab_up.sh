#!/usr/bin/env bash
# Start disposable lab SQL, wait healthy, ensure database exists.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

lab_load_env
lab_assert_lab_enabled
lab_assert_loopback_sql
lab_assert_local_storage
lab_assert_no_real_llm_keys

mkdir -p "${LAB_OUTPUT_DIR}"

echo "==> Starting lab-sql (compose)..."
lab_compose up -d lab-sql

echo "==> Waiting for lab-sql healthy..."
lab_wait_sql_healthy

echo "==> Ensuring database ${SQLSERVER_DATABASE}..."
lab_ensure_database

echo "==> Lab SQL status:"
lab_compose ps
echo "OK: lab-sql listening on 127.0.0.1:14333 (database=${SQLSERVER_DATABASE})"
echo "Next: migrate + seed (see audit/lab/README.md), then run API on 127.0.0.1:18080"
