#!/usr/bin/env bash
# Phase 7 — full security scan suite (no NOT_AVAILABLE). Uses host binaries or pinned containers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

release_require_cmd git docker
release_require_python
release_require_sha

TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.58.1}"
HADOLINT_IMAGE="${HADOLINT_IMAGE:-hadolint/hadolint:v2.12.0-alpine}"
REPORT_DIR="${ROOT}/.tmp/phase7-security"
mkdir -p "${REPORT_DIR}"

API_IMAGE="dinamic-api:${GIT_SHA}"
WORKER_IMAGE="dinamic-worker:${GIT_SHA}"

run_logged() {
  local name="$1"
  shift
  echo ""
  echo "== ${name} =="
  set +e
  "$@"
  local ec=$?
  set -e
  echo "${name}_exit=${ec}"
  [[ "${ec}" -eq 0 ]] || release_die "${name} failed with exit ${ec}"
}

release_log_stage "tool versions"
echo "python=$("${RELEASE_PY}" -V)"
echo "trivy_image=${TRIVY_IMAGE}"
echo "hadolint_image=${HADOLINT_IMAGE}"
if command -v gitleaks >/dev/null 2>&1; then gitleaks version || true; fi
if command -v shellcheck >/dev/null 2>&1; then shellcheck --version | head -1; fi

release_log_stage "ensure images for trivy"
if ! docker image inspect "${API_IMAGE}" >/dev/null 2>&1; then
  docker build -t "${API_IMAGE}" -f "${ROOT}/backend/Dockerfile" "${ROOT}/backend"
fi
if ! docker image inspect "${WORKER_IMAGE}" >/dev/null 2>&1; then
  docker build -t "${WORKER_IMAGE}" -f "${ROOT}/backend/Dockerfile.worker" "${ROOT}/backend"
fi

run_logged pip_audit "${RELEASE_PY}" -m pip_audit
(
  cd "${ROOT}/frontend"
  run_logged frontend_npm_audit npm audit --audit-level=high
)
(
  cd "${ROOT}/mobile"
  run_logged mobile_npm_audit npm audit --audit-level=high
)
run_logged bandit "${RELEASE_PY}" -m bandit -r backend/src scripts -q
run_logged gitleaks_detect gitleaks detect --source "${ROOT}" --redact
run_logged gitleaks_git gitleaks git --redact "${ROOT}"

run_logged trivy_fs docker run --rm -v "${ROOT}:/proj:ro" "${TRIVY_IMAGE}" fs \
  --severity HIGH,CRITICAL --exit-code 1 \
  --skip-dirs .venv --skip-dirs backend/.venv --skip-dirs venv \
  --skip-dirs node_modules --skip-dirs frontend/node_modules --skip-dirs mobile/node_modules \
  --skip-files secrets/gcp-service-account.json \
  /proj

run_logged trivy_api docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  "${TRIVY_IMAGE}" image --severity HIGH,CRITICAL --exit-code 1 "${API_IMAGE}"

run_logged trivy_worker docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  "${TRIVY_IMAGE}" image --severity HIGH,CRITICAL --exit-code 1 "${WORKER_IMAGE}"

run_logged hadolint docker run --rm -v "${ROOT}/backend:/work:ro" "${HADOLINT_IMAGE}" hadolint /work/Dockerfile
run_logged hadolint_worker docker run --rm -v "${ROOT}/backend:/work:ro" "${HADOLINT_IMAGE}" hadolint /work/Dockerfile.worker

run_logged shellcheck shellcheck -e SC2030,SC2031,SC2317,SC2034 scripts/release/*.sh

# Record digests
docker image inspect --format='{{index .RepoDigests 0}}' "${API_IMAGE}" >"${REPORT_DIR}/api.digest" 2>/dev/null \
  || docker image inspect --format='{{.Id}}' "${API_IMAGE}" >"${REPORT_DIR}/api.digest"
docker image inspect --format='{{index .RepoDigests 0}}' "${WORKER_IMAGE}" >"${REPORT_DIR}/worker.digest" 2>/dev/null \
  || docker image inspect --format='{{.Id}}' "${WORKER_IMAGE}" >"${REPORT_DIR}/worker.digest"

echo "SECURITY_SCAN_OK"
echo "api_image=${API_IMAGE}"
echo "worker_image=${WORKER_IMAGE}"
echo "api_digest=$(cat "${REPORT_DIR}/api.digest")"
echo "worker_digest=$(cat "${REPORT_DIR}/worker.digest")"
echo "HEAD=${GIT_SHA}"
