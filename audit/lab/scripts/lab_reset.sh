#!/usr/bin/env bash
# Reset disposable lab: exclusive lock, recreate DB volume (or drop DB), migrate, clean output, seed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

MODE="volume" # volume | database
for arg in "$@"; do
  case "${arg}" in
    --database-only) MODE="database" ;;
    --volume) MODE="volume" ;;
    -h | --help)
      echo "Usage: $0 [--volume|--database-only]"
      exit 0
      ;;
    *) lab_die "Unknown argument: ${arg}" ;;
  esac
done

lab_reset_main() {
  lab_load_env
  bash "${SCRIPT_DIR}/lab_preflight.sh"

  lab_assert_safe_delete_path "${LAB_OUTPUT_DIR}" "LAB_OUTPUT_DIR"

  echo "==> Stopping lab compose..."
  lab_compose stop || true

  if [[ "${MODE}" == "volume" ]]; then
    echo "==> Recreating SQL volume (lab data only)..."
    lab_compose down -v
    lab_compose up -d lab-sql
    lab_wait_sql_healthy
    lab_ensure_database
  else
    echo "==> Drop/recreate database ${SQLSERVER_DATABASE}..."
    lab_compose up -d lab-sql
    lab_wait_sql_healthy
    local db="${SQLSERVER_DATABASE}"
    case "${db}" in
      *[' '\;]* | "") lab_die "Unsafe SQLSERVER_DATABASE" ;;
    esac
    lab_sqlcmd_in_container \
      "ALTER DATABASE [${db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [${db}];" \
      || true
    lab_ensure_database
  fi

  echo "==> Cleaning lab output under ${LAB_OUTPUT_DIR}..."
  mkdir -p "${LAB_OUTPUT_DIR}"
  find "${LAB_OUTPUT_DIR}" -mindepth 1 -maxdepth 5 -print0 2>/dev/null | while IFS= read -r -d '' p; do
    lab_assert_safe_delete_path "${p}" "lab output entry"
    rm -rf "${p}"
  done
  rm -f "${LAB_DATA_DIR}/seed.ok" \
    "${LAB_DATA_DIR}/fixture-tokens.json" \
    "${LAB_DATA_DIR}/runtime-manifest.json"

  echo "==> Migrating schema (schema.sql bootstrap + db_migrate apply)..."
  bash "${SCRIPT_DIR}/lab_bootstrap_schema.sh"

  echo "==> Seeding fixtures..."
  (
    cd "${REPO_ROOT}/backend"
    set -a
    # shellcheck disable=SC1090
    source "${LAB_ENV_FILE}"
    set +a
    "${REPO_ROOT}/backend/.venv/bin/python" "${LAB_ROOT}/scripts/seed_lab.py"
  )

  [[ -f "${LAB_DATA_DIR}/seed.ok" ]] || lab_die "seed.ok missing after seed"
  echo "OK: lab reset complete (mode=${MODE})"
}

lab_with_lock exclusive lab_reset_main
