#!/usr/bin/env bash
# Shared helpers for disposable Phase 4B lab scripts (fail-closed).
# shellcheck shell=bash

set -euo pipefail

_LAB_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_ROOT="$(cd "${_LAB_LIB_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${LAB_ROOT}/../.." && pwd)"
LAB_COMPOSE_FILE="${LAB_ROOT}/docker-compose.lab.yml"
LAB_ENV_FILE="${LAB_ROOT}/.env.lab"
LAB_ENV_EXAMPLE="${LAB_ROOT}/.env.lab.example"
LAB_LOCK_FILE="${LAB_ROOT}/.lab.lock"
LAB_DATA_DIR="${LAB_ROOT}/data"
LAB_OUTPUT_DIR="${LAB_DATA_DIR}/output"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-dinamic-gemini-lab}"

lab_die() {
  echo "ERROR: $*" >&2
  exit 1
}

lab_require_env_file() {
  if [[ ! -f "${LAB_ENV_FILE}" ]]; then
    lab_die "Missing ${LAB_ENV_FILE}. Copy from ${LAB_ENV_EXAMPLE} and edit."
  fi
}

lab_load_env() {
  lab_require_env_file
  set -a
  # shellcheck disable=SC1090
  source "${LAB_ENV_FILE}"
  set +a
  # Prevent developer repo .env from clobbering lab SQL/storage during Python loads.
  # (src.config still loads .env without override for unset keys; critical lab keys must be set above.)
  export LAB_ENV_LOADED=1
}

lab_compose() {
  docker compose -f "${LAB_COMPOSE_FILE}" --env-file "${LAB_ENV_FILE}" --project-name "${COMPOSE_PROJECT_NAME}" "$@"
}

lab_assert_safe_delete_path() {
  local target="${1:-}"
  local label="${2:-path}"
  if [[ -z "${target}" ]]; then
    lab_die "Refusing to delete empty ${label}"
  fi
  local resolved="${target}"
  if [[ -e "${target}" ]]; then
    resolved="$(cd "$(dirname "${target}")" && pwd)/$(basename "${target}")"
  elif [[ "${target}" = /* ]]; then
    resolved="${target}"
  else
    resolved="${LAB_DATA_DIR}/${target}"
  fi
  case "${resolved}" in
    / | /Users | /home | "${HOME}" | "${HOME}/" | "${REPO_ROOT}" | "${REPO_ROOT}/")
      lab_die "Refusing dangerous ${label}: ${resolved}"
      ;;
  esac
  case "${resolved}" in
    "${LAB_DATA_DIR}" | "${LAB_DATA_DIR}"/* | "${LAB_ROOT}/data" | "${LAB_ROOT}/data"/*) ;;
    *)
      lab_die "Refusing ${label} outside lab data dir: ${resolved}"
      ;;
  esac
}

lab_with_lock() {
  local mode="${1:-exclusive}"
  shift
  mkdir -p "${LAB_ROOT}"
  if command -v flock >/dev/null 2>&1; then
    if [[ "${mode}" == "shared" ]]; then
      flock -s "${LAB_LOCK_FILE}" "$@"
    else
      flock "${LAB_LOCK_FILE}" "$@"
    fi
  else
    # macOS often lacks flock; use mkdir lock directory.
    local lockdir="${LAB_LOCK_FILE}.d"
    local waited=0
    while ! mkdir "${lockdir}" 2>/dev/null; do
      slept=1
      sleep 1
      waited=$((waited + 1))
      if [[ "${waited}" -gt 120 ]]; then
        lab_die "Could not acquire lab lock at ${lockdir}"
      fi
    done
    trap 'rmdir "${lockdir}" 2>/dev/null || true' EXIT
    "$@"
    rmdir "${lockdir}" 2>/dev/null || true
    trap - EXIT
  fi
}

lab_is_truthy() {
  case "${1:-}" in
    true | TRUE | True | 1 | yes | YES | Yes) return 0 ;;
    *) return 1 ;;
  esac
}

lab_sqlcmd_in_container() {
  local query="$1"
  local pwd="${MSSQL_SA_PASSWORD:-${SQLSERVER_PWD:-}}"
  [[ -n "${pwd}" ]] || lab_die "MSSQL_SA_PASSWORD / SQLSERVER_PWD empty"
  lab_compose exec -T lab-sql bash -lc \
    "(/opt/mssql-tools18/bin/sqlcmd -S 127.0.0.1 -U sa -P $(printf '%q' "${pwd}") -C -Q $(printf '%q' "${query}") 2>/dev/null) \
     || (/opt/mssql-tools/bin/sqlcmd -S 127.0.0.1 -U sa -P $(printf '%q' "${pwd}") -C -Q $(printf '%q' "${query}"))"
}

lab_wait_sql_healthy() {
  local i
  for i in $(seq 1 60); do
    if lab_compose ps --status running --format '{{.Health}}' 2>/dev/null | grep -qi healthy; then
      return 0
    fi
    # Fallback: try SELECT 1
    if lab_sqlcmd_in_container "SELECT 1" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  lab_die "lab-sql did not become healthy in time"
}

lab_ensure_database() {
  local db="${SQLSERVER_DATABASE:-dinamic_gemini_lab}"
  [[ -n "${db}" ]] || lab_die "SQLSERVER_DATABASE empty"
  case "${db}" in
    *[' '\;]*) lab_die "Unsafe SQLSERVER_DATABASE value" ;;
  esac
  lab_sqlcmd_in_container \
    "IF DB_ID(N'${db}') IS NULL CREATE DATABASE [${db}];"
}

# Provider / key fail-closed checks (shared by preflight + attestation scripts).
lab_assert_no_real_llm_keys() {
  local marker="${LAB_FIXTURE_KEY_MARKER:-lab-fixture-only}"
  local key name
  for name in GEMINI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY; do
    key="${!name:-}"
    if [[ -z "${key}" ]]; then
      continue
    fi
    if [[ "${key}" == "${marker}" ]]; then
      continue
    fi
    lab_die "${name} is set to a non-fixture value. Unset it or set LAB_LLM_MOCKED + fixture marker only."
  done
  if ! lab_is_truthy "${LAB_LLM_MOCKED:-}"; then
    lab_die "LAB_LLM_MOCKED must be true for disposable lab"
  fi
}

lab_assert_loopback_sql() {
  local server="${SQLSERVER_SERVER:-}"
  [[ -n "${server}" ]] || lab_die "SQLSERVER_SERVER empty"
  case "${server}" in
    127.0.0.1,* | 127.0.0.1 | localhost,* | localhost | ::1,* | ::1) ;;
    *)
      lab_die "SQLSERVER_SERVER must be loopback for lab (got: ${server})"
      ;;
  esac
}

lab_assert_local_storage() {
  local provider
  provider="$(echo "${ARTIFACT_STORAGE_PROVIDER:-local}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${provider}" != "local" ]]; then
    lab_die "ARTIFACT_STORAGE_PROVIDER must be local for lab (got: ${provider})"
  fi
  local out="${OUTPUT_DIR:-}"
  [[ -n "${out}" ]] || lab_die "OUTPUT_DIR empty"
}

lab_assert_lab_enabled() {
  lab_is_truthy "${LAB_DISPOSABLE_ENABLED:-}" || lab_die "LAB_DISPOSABLE_ENABLED must be true"
  case "${V3_RUNTIME_ENVIRONMENT:-${APP_ENV:-}}" in
    local | LOCAL | test | TEST | testing | pytest | ci) ;;
    *)
      lab_die "Lab requires V3_RUNTIME_ENVIRONMENT/APP_ENV in {local,test} (got: ${V3_RUNTIME_ENVIRONMENT:-${APP_ENV:-}})"
      ;;
  esac
}
