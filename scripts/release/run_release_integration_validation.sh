#!/usr/bin/env bash
# Phase 7 — release *integration* validation (pytest integration + architecture suites).
# Formerly mislabeled as E2E. Real E2E lives in run_e2e_release_validation.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=scripts/release/_common.sh
source "${ROOT}/scripts/release/_common.sh"

release_require_cmd git
release_require_python
release_require_sha

release_log_stage "release integration validation"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

echo "--- SQL integration (claim, lease, recovery) ---"
"${RELEASE_PY}" -m pytest backend/tests/integration -q --no-cov

echo "--- fencing + recovery characterization ---"
"${RELEASE_PY}" -m pytest \
  backend/tests/integration/jobs \
  backend/tests/integration/recovery \
  backend/tests/architecture \
  -q --no-cov

echo "--- process aisle structured config errors ---"
"${RELEASE_PY}" -m pytest \
  backend/tests/api/test_error_mapping.py::test_start_aisle_processing_supplier_prompt_required_returns_422 \
  -q --no-cov

echo "RELEASE_INTEGRATION_VALIDATION_OK"
echo "HEAD=${GIT_SHA}"
