#!/usr/bin/env bash
# Phase 7 — release E2E validation using existing automated suites (no live LLM spend).
# Full production photo→LLM E2E remains an ops runbook item with a synthetic tenant.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${AUDIT_PYTHON:-$ROOT/backend/.venv/bin/python}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

echo "== Phase 7 E2E release validation =="
echo "HEAD=$(git rev-parse HEAD)"

echo "--- SQL integration (claim, lease, recovery) ---"
"$PY" -m pytest backend/tests/integration -q --no-cov

echo "--- fencing + recovery characterization ---"
"$PY" -m pytest \
  backend/tests/integration/jobs \
  backend/tests/integration/recovery \
  backend/tests/architecture \
  -q --no-cov

echo "--- process aisle structured config errors ---"
"$PY" -m pytest \
  backend/tests/api/test_error_mapping.py::test_start_aisle_processing_supplier_prompt_required_returns_422 \
  -q --no-cov

echo "E2E_RELEASE_VALIDATION_OK"
echo "NOTE: Live inventory→images→LLM path is documented in audit-results/phase-7/end-to-end-test-report.md"
