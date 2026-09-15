#!/usr/bin/env bash
# Point audit/lab/.env.lab at a schema-only cloned disposable DB on the local
# loopback SQL instance (default 127.0.0.1 / localhost).
# Does NOT print passwords. Does NOT touch DEV/staging/prod remote hosts.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

lab_require_env_file
REPO_ENV="${REPO_ROOT}/.env"
[[ -f "${REPO_ENV}" ]] || lab_die "Missing ${REPO_ENV} (needed for local SA credentials to clone instance)"

# Extract values without sourcing (avoid .env executing weird lines)
_get() {
  local key="$1" file="$2"
  local line
  line="$(grep -E "^${key}=" "${file}" | tail -1 || true)"
  printf '%s' "${line#${key}=}"
}

src_server="$(_get SQLSERVER_SERVER "${REPO_ENV}")"
src_uid="$(_get SQLSERVER_UID "${REPO_ENV}")"
src_pwd="$(_get SQLSERVER_PWD "${REPO_ENV}")"
src_driver="$(_get SQLSERVER_DRIVER "${REPO_ENV}")"
[[ -n "${src_pwd}" ]] || lab_die "SQLSERVER_PWD missing in repo .env"
host="${src_server%%,*}"
host="${host:-localhost}"
case "${host}" in
  127.0.0.1|localhost|::1) ;;
  *) lab_die "Refusing non-loopback SQLSERVER_SERVER=${src_server}" ;;
esac

# Rewrite lab env SQL block (preserve other keys)
tmp="$(mktemp)"
# shellcheck disable=SC2016
awk -v server="${host}" -v uid="${src_uid:-sa}" -v driver="${src_driver:-ODBC Driver 17 for SQL Server}" '
  BEGIN { done=0 }
  /^SQLSERVER_SERVER=/ { print "SQLSERVER_SERVER=" server; next }
  /^SQLSERVER_DATABASE=/ { print "SQLSERVER_DATABASE=dinamic_gemini_lab"; next }
  /^SQLSERVER_UID=/ { print "SQLSERVER_UID=" uid; next }
  /^SQLSERVER_DRIVER=/ { print "SQLSERVER_DRIVER='\''" driver "'\''"; next }
  /^SQLSERVER_PWD=/ { next }
  /^MSSQL_SA_PASSWORD=/ { next }
  { print }
  END { }
' "${LAB_ENV_FILE}" > "${tmp}"

# Append secrets at end (gitignored file only)
{
  cat "${tmp}"
  echo "SQLSERVER_PWD=${src_pwd}"
  echo "MSSQL_SA_PASSWORD=${src_pwd}"
  echo "LAB_SQL_MODE=cloned_schema_on_loopback_instance"
} > "${LAB_ENV_FILE}"
rm -f "${tmp}"

echo "OK: .env.lab now targets loopback SQL database dinamic_gemini_lab (cloned schema mode)."
echo "    Server host: ${host} (password not printed)"
