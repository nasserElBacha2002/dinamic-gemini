#!/usr/bin/env bash
# DIN-508 Phase 2 corrections — focused validation + evidence under DIN-508/phase-2/corrections/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
OUT="${REPO}/DIN-508/phase-2/corrections"
TESTS_OUT="${OUT}/implementation-corrections-tests.txt"
mkdir -p "$OUT"

{
  echo "=== channel_id unit tests ==="
  cd "$ROOT"
  if [[ -x "$REPO/.venv/bin/pytest" ]]; then
    "$REPO/.venv/bin/pytest" tests/ -q --tb=short
  else
    pytest tests/ -q --tb=short
  fi
  echo ""
  echo "=== streaming POC (sanitized tail) ==="
  "$ROOT/scripts/run_poc_validation.sh" 2>&1 | tail -60
} | tee "$TESTS_OUT"

# Git review artifacts (corrections scope only — see corrections-validation.md)
cd "$REPO"
git add -N .
git --no-pager status --short > "${OUT}/implementation-corrections-status.txt"
git --no-pager diff --stat > "${OUT}/implementation-corrections-diffstat.txt"
git --no-pager diff --find-renames --find-copies -U20 > "${OUT}/implementation-corrections-diff.txt"
echo "Wrote ${OUT}/implementation-corrections-*.txt"