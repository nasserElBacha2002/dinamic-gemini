#!/usr/bin/env sh
# Full audit runner (Phase 0 corrections).
# Collectors may continue after findings; aggregator / gate structural failures fail the run.
set -u

echo "== Quality Gate full audit (Phase 0) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
AUDIT_DIR="$ROOT_DIR/audit"
RAW_DIR="$AUDIT_DIR/raw"
STATUS_PUBLISHED="$AUDIT_DIR/audit-status.json"
SUMMARY_PUBLISHED="$AUDIT_DIR/audit-summary.md"

# shellcheck disable=SC1091
. "$ROOT_DIR/scripts/audit/resolve_python.sh"
if [ -z "${AUDIT_PYTHON:-}" ]; then
  echo "ERROR: no usable Python for audit (set AUDIT_PYTHON or create backend/.venv)" >&2
  exit 2
fi
echo "AUDIT_PYTHON=$AUDIT_PYTHON"

RUN_ID="${AUDIT_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
export AUDIT_RUN_ID="$RUN_ID"
echo "AUDIT_RUN_ID=$RUN_ID"

# Clear published aggregates so a failed generator cannot leave / expose stale status.
rm -f "$STATUS_PUBLISHED" "$SUMMARY_PUBLISHED"
echo "Cleared published aggregates (audit-status.json / audit-summary.md)"

COLLECTOR_RC=0
run_collector() {
  rel="$1"
  abs="$ROOT_DIR/$rel"
  if [ ! -f "$abs" ]; then
    echo "--- No encontrado (omitido): $rel"
    return 0
  fi
  echo "--- Ejecutando: $rel"
  if [ "${rel##*.}" = "py" ]; then
    "$AUDIT_PYTHON" "$abs"
  else
    bash "$abs"
  fi
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "--- Collector exited $rc (findings/errors recorded; continuing)"
    # Collectors keep going; structural failure is only aggregator/gate.
    COLLECTOR_RC=1
  fi
  return 0
}

if [ "${AUDIT_PHASE0_SKIP_COLLECTORS:-0}" != "1" ]; then
  run_collector "scripts/audit/run_backend_audit.sh"
  run_collector "scripts/audit/run_frontend_audit.sh"
  run_collector "scripts/audit/run_mobile_audit.sh"
  run_collector "scripts/audit/run_backend_architecture_audit.sh"
  run_collector "scripts/audit/run_frontend_architecture_audit.sh"
else
  echo "--- AUDIT_PHASE0_SKIP_COLLECTORS=1: skipping area runners"
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dinamic-audit.XXXXXX")"
STATUS_TMP="$TMP_DIR/audit-status.json"
SUMMARY_TMP="$TMP_DIR/audit-summary.md"
GENERATOR_RC=0

echo "--- Ejecutando: scripts/audit/generate_audit_summary.py (atomic publish)"
"$AUDIT_PYTHON" "$ROOT_DIR/scripts/audit/generate_audit_summary.py" \
  --status-out "$STATUS_TMP" \
  --summary-out "$SUMMARY_TMP" \
  --run-id "$RUN_ID"
GENERATOR_RC=$?
if [ "$GENERATOR_RC" -ne 0 ]; then
  echo "ERROR: generate_audit_summary.py failed (rc=$GENERATOR_RC)" >&2
  echo "Published aggregates were not written; gate will not see stale status." >&2
  rm -rf "$TMP_DIR"
  # Snapshot raw evidence even on aggregator failure for debugging.
  RUNS_DIR="$RAW_DIR/runs"
  rm -rf "$RUNS_DIR"
  ARCH="$RUNS_DIR/$RUN_ID"
  mkdir -p "$ARCH"
  for f in "$RAW_DIR"/*; do
    [ -f "$f" ] || continue
    bn="$(basename "$f")"
    case "$bn" in
      .gitkeep|LATEST_RUN.txt) continue ;;
    esac
    cp "$f" "$ARCH/" 2>/dev/null || true
  done
  printf '%s\n' "$RUN_ID" > "$RAW_DIR/LATEST_RUN.txt"
  exit "$GENERATOR_RC"
fi

# Atomic publish only after successful generation.
mv "$STATUS_TMP" "$STATUS_PUBLISHED"
mv "$SUMMARY_TMP" "$SUMMARY_PUBLISHED"
rm -rf "$TMP_DIR"
echo "Published aggregates for run_id=$RUN_ID"

# Version raw snapshot for this run (last snapshot only).
RUNS_DIR="$RAW_DIR/runs"
if [ -d "$RUNS_DIR" ]; then
  echo "Eliminando snapshot raw anterior (audit/raw/runs/)"
  rm -rf "$RUNS_DIR"
fi
ARCH="$RUNS_DIR/$RUN_ID"
mkdir -p "$ARCH"
for f in "$RAW_DIR"/*; do
  [ -f "$f" ] || continue
  bn="$(basename "$f")"
  case "$bn" in
    .gitkeep|LATEST_RUN.txt) continue ;;
  esac
  cp "$f" "$ARCH/"
done
printf '%s\n' "$RUN_ID" > "$RAW_DIR/LATEST_RUN.txt"
echo "Snapshot raw de esta corrida: audit/raw/runs/$RUN_ID"

GATE_RC=0
echo "--- Ejecutando: scripts/audit/enforce_quality_gate.py --strict"
"$AUDIT_PYTHON" "$ROOT_DIR/scripts/audit/enforce_quality_gate.py" --strict
GATE_RC=$?
if [ "$GATE_RC" -ne 0 ]; then
  echo "Quality Gate FAIL (rc=$GATE_RC)"
else
  echo "Quality Gate PASS"
fi

echo
echo "Consolidación disponible en:"
echo "- $SUMMARY_PUBLISHED"
echo "- $STATUS_PUBLISHED"
echo "run_id=$RUN_ID"

# Structural outcome: generator already exited on failure; propagate gate.
# Collector findings alone do not override a passing gate.
if [ "$GATE_RC" -ne 0 ]; then
  exit "$GATE_RC"
fi
exit 0
