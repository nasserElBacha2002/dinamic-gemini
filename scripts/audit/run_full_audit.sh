#!/usr/bin/env sh
set -u

echo "== Quality Gate full audit (Fase 4) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

run_if_exists() {
  rel="$1"
  abs="$ROOT_DIR/$rel"
  if [ -f "$abs" ]; then
    echo "--- Ejecutando: $rel"
    if [ "${rel##*.}" = "py" ]; then
      python3 "$abs" || true
    else
      bash "$abs" || true
    fi
  else
    echo "--- No encontrado (omitido): $rel"
  fi
}

run_if_exists "scripts/audit/run_backend_audit.sh"
run_if_exists "scripts/audit/run_frontend_audit.sh"
run_if_exists "scripts/audit/run_backend_architecture_audit.sh"
run_if_exists "scripts/audit/run_frontend_architecture_audit.sh"
run_if_exists "scripts/audit/generate_audit_summary.py"

# Versionar salidas raw de esta corrida (copia de los archivos planos en audit/raw/).
# La consolidación lee siempre los nombres fijos en audit/raw/; el historial queda en audit/raw/runs/<id>/
RUN_ID="$(date +%Y%m%d-%H%M%S)"
ARCH="$ROOT_DIR/audit/raw/runs/$RUN_ID"
mkdir -p "$ARCH"
for f in "$ROOT_DIR/audit/raw"/*; do
  [ -f "$f" ] || continue
  bn="$(basename "$f")"
  case "$bn" in
    .gitkeep|LATEST_RUN.txt) continue ;;
  esac
  cp "$f" "$ARCH/"
done
printf '%s\n' "$RUN_ID" > "$ROOT_DIR/audit/raw/LATEST_RUN.txt"
echo "Snapshot raw de esta corrida: audit/raw/runs/$RUN_ID"

if [ -f "$ROOT_DIR/scripts/audit/enforce_quality_gate.py" ]; then
  echo "--- Ejecutando: scripts/audit/enforce_quality_gate.py"
  python3 "$ROOT_DIR/scripts/audit/enforce_quality_gate.py"
  GATE_RC="$?"
  if [ "$GATE_RC" -ne 0 ]; then
    echo "Quality Gate en FAIL (modo no bloqueante). Continuando en Fase 5."
  fi
else
  echo "--- No encontrado (omitido): scripts/audit/enforce_quality_gate.py"
fi

echo
echo "Consolidación disponible en:"
echo "- $ROOT_DIR/audit/audit-summary.md"
echo "- $ROOT_DIR/audit/audit-status.json"

exit 0
