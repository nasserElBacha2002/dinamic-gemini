#!/usr/bin/env bash
# Phase 7 — non-destructive smoke checks (no production mutations).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${AUDIT_PYTHON:-$ROOT/backend/.venv/bin/python}"
export PYTHONPATH="${ROOT}:${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

echo "== Phase 7 smoke =="
echo "HEAD=$(git rev-parse HEAD)"

echo "--- import app + /health + /ready via TestClient ---"
"$PY" - <<'PY'
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app, raise_server_exceptions=False)
h = client.get("/health")
assert h.status_code == 200, h.text
assert isinstance(h.json(), dict)
r = client.get("/ready")
assert r.status_code in (200, 503), r.text
print("health", h.status_code, "ready", r.status_code)
PY

echo "--- recovery dry-run CLI help ---"
"$PY" -m scripts.ops.recover_job --help >/dev/null
"$PY" -m scripts.ops.inspect_job --help >/dev/null
"$PY" -m scripts.ops.inspect_aisle --help >/dev/null
"$PY" -m scripts.ops.preflight_0073_retry_of_duplicates --help >/dev/null

echo "--- targeted pytest smoke surface ---"
"$PY" -m pytest \
  backend/tests/api/test_health_ready_repository_backend_phase2.py \
  backend/tests/observability/test_recover_stale_job.py \
  backend/tests/architecture/test_phase6_persist_fence_characterization.py \
  -q --no-cov

echo "SMOKE_OK"
