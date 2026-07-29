#!/usr/bin/env bash
# Phase 4 corrections — Docker non-root smoke (API + worker images).
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
API_TAG="${DINAMIC_API_SMOKE_TAG:-dinamic-api-p4-smoke:local}"
WORKER_TAG="${DINAMIC_WORKER_SMOKE_TAG:-dinamic-worker-p4-smoke:local}"

echo "== docker build API =="
docker build -f "$ROOT/backend/Dockerfile" -t "$API_TAG" "$ROOT/backend"

echo "== docker build worker =="
docker build -f "$ROOT/backend/Dockerfile.worker" -t "$WORKER_TAG" "$ROOT/backend"

echo "== API non-root + /health =="
docker run --rm --user 10001:10001 -d --name dinamic-p4-api-smoke -p 18000:8000 \
  -e V3_RUNTIME_ENVIRONMENT=test \
  -e EMBEDDED_WORKER_ENABLED=false \
  -e SQLSERVER_ENABLED=false \
  "$API_TAG" >/tmp/dinamic-p4-api-cid.txt
trap 'docker rm -f dinamic-p4-api-smoke >/dev/null 2>&1 || true' EXIT
sleep 3
curl -fsS "http://127.0.0.1:18000/health" | grep -q '"ok"'
WHOAMI="$(docker exec dinamic-p4-api-smoke id -u)"
test "$WHOAMI" = "10001"
docker exec dinamic-p4-api-smoke tesseract --list-langs | grep -E 'spa|eng'
docker exec dinamic-p4-api-smoke python -c "from pyzbar.pyzbar import decode; print('pyzbar-ok')"
docker exec dinamic-p4-api-smoke sh -c 'touch /app/output/p4-smoke-write && rm /app/output/p4-smoke-write'

echo "== worker non-root startup (import path) =="
docker run --rm --user 10001:10001 \
  -e V3_RUNTIME_ENVIRONMENT=test \
  -e SQLSERVER_ENABLED=false \
  "$WORKER_TAG" \
  python -c "import src.jobs.run_worker as w; import os; assert os.getuid()==10001; print('worker-ok')"

echo "Docker smoke OK (uid=10001)"
