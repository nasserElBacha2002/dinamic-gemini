#!/usr/bin/env bash
# DIN-508 Phase 2 — final technical closure (focused validation + review artifacts).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="${REPO}/DIN-508/phase-2/corrections"
POC="$(cd "$(dirname "$0")/.." && pwd)"
TESTS_OUT="${OUT}/final-corrections-tests.txt"
VALIDATION_MD="${OUT}/final-corrections-validation.md"

mkdir -p "$OUT" review

{
  echo "=== self-test: deliberate assertion must exit 1 ==="
  set +e
  POC_VALIDATION_SELF_TEST_ASSERT=1 bash "$POC/scripts/run_poc_validation.sh" >/tmp/poc-selftest.out 2>&1
  st=$?
  set -e
  echo "self_test_exit_code=$st"
  [[ "$st" -eq 1 ]] || { echo "FAIL: self-test expected exit 1"; exit 1; }

  echo ""
  echo "=== pytest channel_id ==="
  if [[ -x "$REPO/.venv/bin/pytest" ]]; then
    "$REPO/.venv/bin/pytest" "$POC/tests/" -q --tb=short --no-cov
  else
    pytest "$POC/tests/" -q --tb=short
  fi

  echo ""
  echo "=== SQL literal collation probe ==="
  if [[ -x "$REPO/.venv/bin/python" ]]; then
  "$REPO/.venv/bin/python" "$POC/scripts/run_sql_collation_probe.py"
  else
    python3 "$POC/scripts/run_sql_collation_probe.py"
  fi

  echo ""
  echo "=== streaming POC (strict) ==="
  bash "$POC/scripts/run_poc_validation.sh"
} 2>&1 | tee "$TESTS_OUT"

cd "$REPO"
git add -N .
git --no-pager status --short > "${OUT}/final-corrections-status.txt"
git --no-pager diff --stat > "${OUT}/final-corrections-diffstat.txt"
git --no-pager diff --find-renames --find-copies -U20 > "${OUT}/final-corrections-diff.txt"

cp "${OUT}/final-corrections-status.txt" review/latest-status.txt
cp "${OUT}/final-corrections-diffstat.txt" review/latest-diffstat.txt
cp "${OUT}/final-corrections-diff.txt" review/latest-diff.txt
cp review/latest-status.txt review/din-508-final-corrections-status.txt
cp review/latest-diffstat.txt review/din-508-final-corrections-diffstat.txt
cp review/latest-diff.txt review/din-508-final-corrections-diff.txt

cat > "$VALIDATION_MD" <<'MD'
# DIN-508 Phase 2 — Final corrections validation

**Closure:** `PHASE_2_CORRECTED_PENDING_PHYSICAL_VALIDATION`

## Executed
- `POC_VALIDATION_SELF_TEST_ASSERT=1` → exit **1** (proved)
- `pytest infrastructure/din-508-mediamtx/tests/`
- `run_sql_collation_probe.py` (literals + collation)
- `run_poc_validation.sh` (strict assertions, overridePublisher=no)

## Key fixes
- Validation script fails on unauthorized publish success, HTTP mismatches, missing segments, health timeouts
- `overridePublisher: no` — second publisher rejected; republication after first ends
- `channel_id`: `uuid.UUID` canonicalization; max length 64; SQL literal equivalence probes
- Ports bound `127.0.0.1` by default (`MTX_BIND_HOST` override for trusted LAN)
- Credential uniqueness / reserved user rejection in render script

## Residual
- DJI Fly RTMP query auth not field-validated
- Unicode edge cases (accents, ß) may differ Python vs SQL — integration must not assume slug match without SQL check

Evidence: `final-corrections-tests.txt` (sanitized streaming in `final-corrections-tests-streaming.txt`).
MD

echo "Closure artifacts: ${OUT}/final-corrections-*"