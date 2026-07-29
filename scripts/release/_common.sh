#!/usr/bin/env bash
# Shared helpers for Phase 7 release scripts. Source only — do not execute.
# shellcheck shell=bash

set -euo pipefail

if [[ -n "${_DINAMIC_RELEASE_COMMON_LOADED:-}" ]]; then
  return 0
fi
_DINAMIC_RELEASE_COMMON_LOADED=1

RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export RELEASE_ROOT

RELEASE_PY="${AUDIT_PYTHON:-${RELEASE_ROOT}/backend/.venv/bin/python}"
export RELEASE_PY

GIT_SHA="$(git -C "${RELEASE_ROOT}" rev-parse HEAD)"
export GIT_SHA

# Ephemeral DB names (never production / never dinamic-gemini).
export PHASE7_SQL_DATABASE="${PHASE7_SQL_DATABASE:-dinamic_phase7_release_test}"
export PHASE7_SQL_UPGRADE_DATABASE="${PHASE7_SQL_UPGRADE_DATABASE:-dinamic_phase7_upgrade_test}"
export PHASE7_SQL_RESTORE_DATABASE="${PHASE7_SQL_RESTORE_DATABASE:-dinamic_phase7_restore_test}"
export PHASE7_SQL_BACKUP_DATABASE="${PHASE7_SQL_BACKUP_DATABASE:-dinamic_phase7_backup_src}"

release_die() {
  echo "ERROR: $*" >&2
  exit 1
}

release_require_cmd() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || release_die "missing required command: $c"
  done
}

release_require_python() {
  [[ -x "${RELEASE_PY}" ]] || release_die "Python not executable: ${RELEASE_PY}"
  "${RELEASE_PY}" -c 'import sys; assert sys.version_info >= (3, 11), sys.version'
}

release_require_sha() {
  [[ -n "${GIT_SHA}" ]] || release_die "unable to resolve GIT_SHA"
  [[ "${#GIT_SHA}" -eq 40 ]] || release_die "GIT_SHA looks invalid: ${GIT_SHA}"
}

release_capture_sql_base_credentials() {
  # Load developer .env once (no lock) and export SERVER/UID/PWD for ephemeral DBs.
  unset DINAMIC_PYTEST_DOTENV_LOCKED || true
  # shellcheck disable=SC1090
  eval "$(
    cd "${RELEASE_ROOT}/backend"
    PYTHONPATH="${RELEASE_ROOT}/backend" "${RELEASE_PY}" - <<'PY'
import os
import shlex
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

r = resolve_sqlserver_connection_config()
if not r.connection_string.strip():
    raise SystemExit("SQL Server credentials not configured")
server = (os.getenv("SQLSERVER_SERVER") or "").strip()
uid = (os.getenv("SQLSERVER_UID") or "").strip()
pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
if not (server and uid and pwd):
    # Fall back to parsing connection string keys (no secret print beyond export).
    parts = {}
    for chunk in r.connection_string.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip().upper()] = v.strip()
    server = server or parts.get("SERVER", "")
    uid = uid or parts.get("UID", "")
    pwd = pwd or parts.get("PWD", "") or parts.get("PASSWORD", "")
if not (server and uid and pwd):
    raise SystemExit("Could not resolve SQLSERVER_SERVER/UID/PWD for ephemeral release DB")
print(f"export SQLSERVER_SERVER={shlex.quote(server)}")
print(f"export SQLSERVER_UID={shlex.quote(uid)}")
print(f"export SQLSERVER_PWD={shlex.quote(pwd)}")
print("export SQLSERVER_ENABLED=true")
print("export SQLSERVER_TRUST_SERVER_CERTIFICATE=yes")
print("export APP_ENV=development")
PY
  )"
}

release_export_ephemeral_sql_env() {
  local database="${1:-${PHASE7_SQL_DATABASE}}"
  [[ -n "${SQLSERVER_SERVER:-}" && -n "${SQLSERVER_UID:-}" && -n "${SQLSERVER_PWD:-}" ]] \
    || release_die "call release_capture_sql_base_credentials before export"
  # Prevent backend/.env from overriding ephemeral SQLSERVER_* .
  export DINAMIC_PYTEST_DOTENV_LOCKED=1
  export SQLSERVER_ENABLED=true
  export SQLSERVER_DATABASE="${database}"
  unset SQLSERVER_CONNECTION_STRING || true
  export PYTHONPATH="${RELEASE_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
  export DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST="${database},${PHASE7_SQL_DATABASE},${PHASE7_SQL_UPGRADE_DATABASE},${PHASE7_SQL_RESTORE_DATABASE},${PHASE7_SQL_BACKUP_DATABASE}"
  export DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER=0
  export APP_ENV="${APP_ENV:-development}"
  export V3_ALLOW_IN_MEMORY_FALLBACK=false
  export DB_SCHEMA_REQUIRED_VERSION="${DB_SCHEMA_REQUIRED_VERSION:-0073}"
  export SQLSERVER_TRUST_SERVER_CERTIFICATE="${SQLSERVER_TRUST_SERVER_CERTIFICATE:-yes}"
}

release_sql_target_safe() {
  echo "server=${SQLSERVER_SERVER:-?} database=${SQLSERVER_DATABASE:-?} uid=${SQLSERVER_UID:-?}"
}

release_ensure_sql_available() {
  release_capture_sql_base_credentials
  release_export_ephemeral_sql_env master
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE=master \
  "${RELEASE_PY}" - <<'PY'
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.database.sqlserver import SqlServerClient
r = resolve_sqlserver_connection_config()
assert r.connection_string.strip(), "SQL unavailable"
client = SqlServerClient(r.connection_string)
with client.cursor() as cur:
    cur.execute("SELECT 1")
    assert cur.fetchone()[0] == 1
print("sql_available=ok target=%s" % (r.sql_server_connect_target,))
PY
}

release_create_database() {
  local database="$1"
  [[ "${database}" == *test* || "${database}" == *phase7* ]] \
    || release_die "refusing to create non-test database: ${database}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE=master \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
  SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" \
  SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
  APP_ENV=development \
  "${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
db = """${database}"""
r = resolve_sqlserver_connection_config()
conn = pyodbc.connect(r.connection_string, autocommit=True)
try:
    cur = conn.cursor()
    cur.execute("SELECT DB_ID(?)", (db,))
    row = cur.fetchone()
    if row[0] is None:
        cur.execute(f"CREATE DATABASE [{db}]")
    cur.close()
finally:
    conn.close()
print(f"database_ensured={db}")
PY
}

release_drop_database() {
  local database="$1"
  [[ "${database}" == *test* || "${database}" == *phase7* ]] \
    || release_die "refusing to drop non-test database: ${database}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE=master \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
  SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" \
  SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
  APP_ENV=development \
  "${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
db = """${database}"""
r = resolve_sqlserver_connection_config()
conn = pyodbc.connect(r.connection_string, autocommit=True)
try:
    cur = conn.cursor()
    cur.execute("SELECT DB_ID(?)", (db,))
    row = cur.fetchone()
    if row[0] is not None:
        cur.execute(f"ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        cur.execute(f"DROP DATABASE [{db}]")
    cur.close()
finally:
    conn.close()
print(f"database_dropped={db}")
PY
}

release_db_migrate() {
  local cmd="$1"
  (
    cd "${RELEASE_ROOT}/backend"
    DINAMIC_PYTEST_DOTENV_LOCKED=1 \
    SQLSERVER_ENABLED=true \
    SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
    SQLSERVER_DATABASE="${SQLSERVER_DATABASE}" \
    SQLSERVER_UID="${SQLSERVER_UID}" \
    SQLSERVER_PWD="${SQLSERVER_PWD}" \
    SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
    APP_ENV=development \
    DB_SCHEMA_REQUIRED_VERSION="${DB_SCHEMA_REQUIRED_VERSION:-0073}" \
    PYTHONPATH="${RELEASE_ROOT}/backend" \
    "${RELEASE_PY}" scripts/db_migrate.py "${cmd}"
  )
}

release_index_0073_exists() {
  local database="${1:-${SQLSERVER_DATABASE}}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE="${database}" \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
  SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" \
  SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
  APP_ENV=development \
  "${RELEASE_PY}" - <<'PY'
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.database.sqlserver import SqlServerClient
r = resolve_sqlserver_connection_config()
client = SqlServerClient(r.connection_string)
row = None
with client.cursor() as cur:
    cur.execute(
        """
        SELECT 1 FROM sys.indexes
        WHERE name = N'UX_inventory_jobs_retry_of_job_id'
          AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
        """
    )
    row = cur.fetchone()
raise SystemExit(0 if row is not None else 1)
PY
}

release_rollback_0073() {
  local database="${1:-${SQLSERVER_DATABASE}}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE="${database}" \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
  SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" \
  SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
  APP_ENV=development \
  "${RELEASE_PY}" - <<'PY'
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.database.sqlserver import SqlServerClient
r = resolve_sqlserver_connection_config()
client = SqlServerClient(r.connection_string)
with client.cursor() as cur:
    cur.execute("DROP INDEX IF EXISTS UX_inventory_jobs_retry_of_job_id ON dbo.inventory_jobs")
print("rollback_0073=ok")
PY
  if release_index_0073_exists "${database}"; then
    release_die "rollback 0073 failed: index still present"
  fi
  echo "rollback_0073=verified_absent database=${database}"
}

release_reapply_0073() {
  local database="${1:-${SQLSERVER_DATABASE}}"
  local sql_file="${RELEASE_ROOT}/backend/src/database/migrations/versions/0073_inventory_jobs_retry_of_unique.sql"
  [[ -f "${sql_file}" ]] || release_die "missing ${sql_file}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE="${database}" \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" \
  SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" \
  SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes \
  APP_ENV=development \
  "${RELEASE_PY}" - <<PY
from pathlib import Path
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
from src.database.sqlserver import SqlServerClient

def split_batches(text: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().upper() == "GO":
            batch = "\\n".join(current).strip()
            if batch:
                batches.append(batch)
            current = []
        else:
            current.append(line)
    tail = "\\n".join(current).strip()
    if tail:
        batches.append(tail)
    return batches

sql = Path("""${sql_file}""").read_text(encoding="utf-8")
r = resolve_sqlserver_connection_config()
client = SqlServerClient(r.connection_string)
for batch in split_batches(sql):
    with client.cursor() as cur:
        cur.execute(batch)
print("reapply_0073_sql=ok")
PY
  release_index_0073_exists "${database}" || release_die "reapply 0073 failed: index missing"
  echo "reapply_0073=ok database=${database}"
}

release_preflight_0073() {
  (
    cd "${RELEASE_ROOT}"
    export DINAMIC_PYTEST_DOTENV_LOCKED=1
    export PYTHONPATH="${RELEASE_ROOT}:${RELEASE_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
    export SQLSERVER_ENABLED=true
    export SQLSERVER_SERVER="${SQLSERVER_SERVER}"
    export SQLSERVER_DATABASE="${SQLSERVER_DATABASE}"
    export SQLSERVER_UID="${SQLSERVER_UID}"
    export SQLSERVER_PWD="${SQLSERVER_PWD}"
    export SQLSERVER_TRUST_SERVER_CERTIFICATE=yes
    export APP_ENV=development
    "${RELEASE_PY}" -m scripts.ops.preflight_0073_retry_of_duplicates
  )
}

release_clone_database() {
  local src="$1"
  local dst="$2"
  [[ "${dst}" == *test* || "${dst}" == *phase7* ]] || release_die "refusing clone into non-test db: ${dst}"
  release_drop_database "${dst}"
  PYTHONPATH="${RELEASE_ROOT}/backend" DINAMIC_PYTEST_DOTENV_LOCKED=1 \
  SQLSERVER_DATABASE=master \
  SQLSERVER_SERVER="${SQLSERVER_SERVER}" SQLSERVER_UID="${SQLSERVER_UID}" \
  SQLSERVER_PWD="${SQLSERVER_PWD}" SQLSERVER_ENABLED=true \
  SQLSERVER_TRUST_SERVER_CERTIFICATE=yes APP_ENV=development \
  "${RELEASE_PY}" - <<PY
import pyodbc
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
src, dst = """${src}""", """${dst}"""
conn = pyodbc.connect(resolve_sqlserver_connection_config().connection_string, autocommit=True)
cur = conn.cursor()
cur.execute("SELECT DB_ID(?)", (src,))
if cur.fetchone()[0] is None:
    raise SystemExit(f"clone source missing: {src}")
cur.execute(f"DBCC CLONEDATABASE (N'{src}', N'{dst}')")
cur.execute(f"ALTER DATABASE [{dst}] SET READ_WRITE WITH ROLLBACK IMMEDIATE")
# CLONEDATABASE is schema-only — copy migration history rows so status matches source.
cur.execute(
    f"""
    IF OBJECT_ID(N'[{dst}].dbo.schema_migrations', 'U') IS NOT NULL
       AND OBJECT_ID(N'[{src}].dbo.schema_migrations', 'U') IS NOT NULL
    BEGIN
        DELETE FROM [{dst}].dbo.schema_migrations;
        SET IDENTITY_INSERT [{dst}].dbo.schema_migrations ON;
        INSERT INTO [{dst}].dbo.schema_migrations
            (id, service_name, version, migration_name, checksum_sha256, deployment_id, applied_at)
        SELECT id, service_name, version, migration_name, checksum_sha256, deployment_id, applied_at
        FROM [{src}].dbo.schema_migrations;
        SET IDENTITY_INSERT [{dst}].dbo.schema_migrations OFF;
    END
    """
)
cur.close(); conn.close()
print(f"cloned_schema_only src={src} dst={dst}")
PY
}

release_ensure_phase7_db() {
  # Prefer schema-only clone of a 0073-compatible source (never production writes).
  local src="${PHASE7_CLONE_SOURCE_FULL:-dinamic-gemini}"
  local dst="${1:-${PHASE7_SQL_DATABASE}}"
  release_clone_database "${src}" "${dst}"
  release_export_ephemeral_sql_env "${dst}"
}

release_log_stage() {
  echo ""
  echo "== $* =="
  echo "HEAD=${GIT_SHA}"
  echo "target=$(release_sql_target_safe)"
}
