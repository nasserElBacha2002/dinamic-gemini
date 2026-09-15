#!/usr/bin/env bash
# Fail-closed preflight before lab up / API start / reset.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

lab_load_env
lab_assert_lab_enabled
lab_assert_loopback_sql
lab_assert_local_storage
lab_assert_no_real_llm_keys

# Refuse remote / public provider hostnames if set.
_check_forbidden_hostname() {
  local name="$1"
  local raw="${!1:-}"
  [[ -z "${raw}" ]] && return 0
  local lower
  lower="$(echo "${raw}" | tr '[:upper:]' '[:lower:]')"
  case "${lower}" in
    *generativelanguage.googleapis.com* | *api.openai.com* | *api.anthropic.com* | *openai.azure.com*)
      lab_die "${name} points at a public LLM provider hostname — refuse for lab"
      ;;
    *amazonaws.com* | *storage.googleapis.com* | *blob.core.windows.net*)
      lab_die "${name} looks like remote object storage — refuse for lab"
      ;;
  esac
}

_check_forbidden_hostname GEMINI_API_BASE_URL
_check_forbidden_hostname OPENAI_API_BASE
_check_forbidden_hostname ANTHROPIC_BASE_URL
_check_forbidden_hostname LLM_API_BASE_URL

provider="$(echo "${ARTIFACT_STORAGE_PROVIDER:-local}" | tr '[:upper:]' '[:lower:]')"
[[ "${provider}" == "local" ]] || lab_die "remote storage provider forbidden"

# Refuse non-loopback SQL host tokens
case "${SQLSERVER_SERVER}" in
  *","*) host_part="${SQLSERVER_SERVER%%,*}" ;;
  *) host_part="${SQLSERVER_SERVER}" ;;
esac
case "${host_part}" in
  127.0.0.1 | localhost | ::1) ;;
  *) lab_die "Non-loopback SQL host refused: ${host_part}" ;;
esac

if lab_is_truthy "${V3_ALLOW_IN_MEMORY_FALLBACK:-}"; then
  lab_die "V3_ALLOW_IN_MEMORY_FALLBACK must be false for fail-closed lab SQL"
fi

echo "OK: lab preflight passed (loopback SQL, local storage, mocked LLM)"
