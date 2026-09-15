#!/usr/bin/env bash
# Bootstrap lab DB from backend/src/database/schema.sql then stamp/apply migrations.
# Canonical clean-install path (see backend/scripts/fold_migrations_into_schema.py).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

lab_load_env
bash "${SCRIPT_DIR}/lab_preflight.sh"

SCHEMA_SQL="${REPO_ROOT}/backend/src/database/schema.sql"
[[ -f "${SCHEMA_SQL}" ]] || lab_die "Missing ${SCHEMA_SQL}"

db="${SQLSERVER_DATABASE:-dinamic_gemini_lab}"
pwd="${MSSQL_SA_PASSWORD:-${SQLSERVER_PWD:-}}"
[[ -n "${pwd}" ]] || lab_die "SQL password empty"
case "${db}" in
  *[' '\;]* | "") lab_die "Unsafe SQLSERVER_DATABASE" ;;
esac

echo "==> Ensuring lab-sql is up..."
lab_compose up -d lab-sql
lab_wait_sql_healthy
lab_ensure_database

echo "==> Applying schema.sql into [${db}] via host sqlcmd..."
# -C trusts server cert (lab loopback). -I enables QUOTED_IDENTIFIER (required for filtered indexes).
# -b fail on error. -d target DB.
sqlcmd -S "127.0.0.1,14333" -U sa -P "${pwd}" -C -I -b -d "${db}" -i "${SCHEMA_SQL}"

echo "==> Recording / applying migration markers (idempotent DDL)..."
py="${REPO_ROOT}/backend/.venv/bin/python"
[[ -x "${py}" ]] || lab_die "Missing ${py}"
(
  cd "${REPO_ROOT}/backend"
  set -a
  # shellcheck disable=SC1090
  source "${LAB_ENV_FILE}"
  set +a
  "${py}" scripts/db_migrate.py apply
)

echo "OK: lab schema bootstrap complete"
