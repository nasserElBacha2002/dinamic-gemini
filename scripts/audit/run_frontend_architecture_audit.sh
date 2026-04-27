#!/usr/bin/env sh
set -u

echo "== Quality Gate - Frontend architecture audit (Fase 3.3) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"
mkdir -p "$RAW_DIR"

if [ -d "$ROOT_DIR/frontend" ]; then
  FRONTEND_DIR="$ROOT_DIR/frontend"
elif [ -f "$ROOT_DIR/package.json" ]; then
  FRONTEND_DIR="$ROOT_DIR"
else
  FRONTEND_DIR=""
fi

CODE_SMELLS_REPORT="$RAW_DIR/frontend-code-smells.txt"
COMPLEXITY_REPORT="$RAW_DIR/frontend-complexity.txt"
IMPORT_BOUNDARIES_REPORT="$RAW_DIR/frontend-import-boundaries.txt"
SOLID_REACT_REPORT="$RAW_DIR/frontend-solid-react-audit.md"
DUPLICATION_REPORT="$RAW_DIR/frontend-duplication.txt"
DEAD_CODE_REPORT="$RAW_DIR/frontend-dead-code.txt"

CODE_SMELLS_STATUS="SKIPPED"
COMPLEXITY_STATUS="SKIPPED"
IMPORT_BOUNDARIES_STATUS="SKIPPED"
SOLID_REACT_STATUS="SKIPPED"
DUPLICATION_STATUS="SKIPPED"
DEAD_CODE_STATUS="SKIPPED"

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio frontend detectado: ${FRONTEND_DIR:-NO_ENCONTRADO}"
echo "Directorio de evidencia: $RAW_DIR"
echo

run_with_timeout() {
  _seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$_seconds" "$@"
    return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$_seconds" "$@"
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$_seconds" "$@" <<'PY'
import subprocess
import sys
seconds = int(sys.argv[1])
cmd = sys.argv[2:]
try:
    p = subprocess.run(cmd, timeout=seconds)
    raise SystemExit(p.returncode)
except subprocess.TimeoutExpired:
    raise SystemExit(124)
PY
    return $?
  fi
  "$@"
  return $?
}

append_timeout_note_if_needed() {
  _report="$1"
  if ! command -v timeout >/dev/null 2>&1 && ! command -v gtimeout >/dev/null 2>&1; then
    {
      echo
      echo "Nota: no se detectó timeout/gtimeout en el sistema."
      echo "Recomendación macOS: instalar coreutils para usar gtimeout."
    } >>"$_report"
  fi
}

if [ -z "$FRONTEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
  {
    echo "Frontend no detectado. Auditoría omitida."
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  } >"$CODE_SMELLS_REPORT"
  cp "$CODE_SMELLS_REPORT" "$COMPLEXITY_REPORT"
  cp "$CODE_SMELLS_REPORT" "$IMPORT_BOUNDARIES_REPORT"
  cp "$CODE_SMELLS_REPORT" "$DUPLICATION_REPORT"
  cp "$CODE_SMELLS_REPORT" "$DEAD_CODE_REPORT"
  {
    echo "# Auditoría frontend - SOLID y patrones React"
    echo
    echo "## Alcance"
    echo
    echo "Frontend no detectado. No se pudo ejecutar auditoría."
  } >"$SOLID_REACT_REPORT"
  exit 0
fi

echo "[START] frontend code smells"
{
  echo "# Frontend code smells audit"
  echo "source_dir: $FRONTEND_DIR"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v npm >/dev/null 2>&1 && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "## ESLint"
    run_with_timeout 90 sh -c "cd \"$FRONTEND_DIR\" && npm run lint"
    ESLINT_RC="$?"
    echo "eslint_exit_code=$ESLINT_RC"
    [ "$ESLINT_RC" -eq 124 ] && echo "TIMEOUT"
  else
    echo "ESLint no disponible (npm o package.json faltante)."
    echo "eslint_exit_code=127"
  fi
} >"$CODE_SMELLS_REPORT" 2>&1
if [ -d "$FRONTEND_DIR/src" ]; then
  run_with_timeout 60 sh -c "find \"$FRONTEND_DIR/src\" -type f \( -name '*.tsx' -o -name '*.ts' \) ! -path '*/node_modules/*' ! -path '*/dist/*' ! -path '*/build/*' ! -path '*/coverage/*' ! -path '*/.vite/*' -print0 2>/dev/null | xargs -0 wc -l 2>/dev/null | awk '\$1 > 300 {print \"LARGE_FILE>300: \" \$2 \" (\" \$1 \")\"}'" >>"$CODE_SMELLS_REPORT" 2>&1
  [ "$?" -eq 124 ] && echo "TIMEOUT fallback find/grep (60s)." >>"$CODE_SMELLS_REPORT"
fi
append_timeout_note_if_needed "$CODE_SMELLS_REPORT"
if rg -n "TIMEOUT" "$CODE_SMELLS_REPORT" >/dev/null 2>&1; then
  CODE_SMELLS_STATUS="ERROR"
elif rg -n "eslint_exit_code=127|ESLint no disponible" "$CODE_SMELLS_REPORT" >/dev/null 2>&1; then
  CODE_SMELLS_STATUS="NOT_INSTALLED"
elif rg -n "eslint_exit_code=0" "$CODE_SMELLS_REPORT" >/dev/null 2>&1; then
  CODE_SMELLS_STATUS="OK"
else
  CODE_SMELLS_STATUS="FINDINGS"
fi
echo "[END] frontend code smells"

echo "[START] frontend complexity"
COMPLEXITY_TMP="$RAW_DIR/.frontend_complexity.py"
cat >"$COMPLEXITY_TMP" <<'PY'
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
root = sys.argv[1]
report = sys.argv[2]
src = os.path.join(root, "src")
exts = (".ts", ".tsx")
exclude_parts = {"node_modules", "dist", "build", "coverage", ".vite"}
files = []
for r, _d, fs in os.walk(src):
    parts = set(r.replace("\\", "/").split("/"))
    if parts & exclude_parts:
        continue
    for fn in fs:
        if fn.endswith(exts):
            files.append(os.path.join(r, fn))
summary = defaultdict(int)
large_files = []
for f in files:
    try:
        txt = open(f, "r", encoding="utf-8").read()
    except Exception:
        continue
    rel = f.replace(root + os.sep, "").replace("\\", "/")
    lines = txt.splitlines()
    n_lines = len(lines)
    cond_score = len(re.findall(r"\bif\s*\(|\bfor\s*\(|\bswitch\s*\(", txt))
    summary["files"] += 1
    summary["functions"] += len(re.findall(r"\bfunction\b|=>", txt))
    summary["if_for_switch"] += cond_score
    if n_lines > 300:
        large_files.append((rel, n_lines))
with open(report, "w", encoding="utf-8") as out:
    out.write("# Frontend complexity audit\n")
    out.write(f"generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    out.write("## Resumen\n")
    out.write(f"- files_scanned: {summary['files']}\n")
    out.write(f"- functions_approx: {summary['functions']}\n")
    out.write(f"- conditional_tokens_approx: {summary['if_for_switch']}\n\n")
    out.write("## Archivos > 300 líneas (revisar)\n")
    if not large_files:
        out.write("- No detectados.\n")
    else:
        for rel, ln in sorted(large_files, key=lambda x: x[1], reverse=True)[:80]:
            out.write(f"- {rel}: {ln}\n")
    out.write("\nObservación: auditoría heurística por conteo textual.\n")
PY
run_with_timeout 60 python3 "$COMPLEXITY_TMP" "$FRONTEND_DIR" "$COMPLEXITY_REPORT"
CMP_RC="$?"
rm -f "$COMPLEXITY_TMP"
if [ "$CMP_RC" -eq 124 ]; then
  {
    echo "# Frontend complexity audit"
    echo "TIMEOUT"
  } >"$COMPLEXITY_REPORT"
  COMPLEXITY_STATUS="ERROR"
elif [ "$CMP_RC" -eq 0 ]; then
  COMPLEXITY_STATUS="FINDINGS"
else
  COMPLEXITY_STATUS="ERROR"
fi
append_timeout_note_if_needed "$COMPLEXITY_REPORT"
echo "[END] frontend complexity"

echo "[START] frontend import boundaries"
{
  echo "# Frontend import boundaries audit"
  echo "source_dir: $FRONTEND_DIR/src"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v madge >/dev/null 2>&1; then
    run_with_timeout 90 sh -c "cd \"$FRONTEND_DIR\" && madge --circular src"
    [ "$?" -eq 124 ] && echo "TIMEOUT madge"
  else
    echo "madge no instalado."
  fi
  if command -v depcruise >/dev/null 2>&1; then
    run_with_timeout 90 sh -c "cd \"$FRONTEND_DIR\" && depcruise src"
    [ "$?" -eq 124 ] && echo "TIMEOUT dependency-cruiser"
  else
    echo "dependency-cruiser no instalado."
  fi
} >"$IMPORT_BOUNDARIES_REPORT" 2>&1
run_with_timeout 60 sh -c "find \"$FRONTEND_DIR/src/components\" -type f \( -name '*.tsx' -o -name '*.ts' \) 2>/dev/null | while IFS= read -r f; do grep -nE \"from ['\\\"](\\.\./)*api/|from ['\\\"]@/api/|axios|fetch\\(\" \"\$f\" >/dev/null 2>&1 && echo \"R1 components->api/fetch: \$f\"; done" >>"$IMPORT_BOUNDARIES_REPORT" 2>&1
[ "$?" -eq 124 ] && echo "TIMEOUT fallback find/grep (60s)." >>"$IMPORT_BOUNDARIES_REPORT"
append_timeout_note_if_needed "$IMPORT_BOUNDARIES_REPORT"
if rg -n "TIMEOUT" "$IMPORT_BOUNDARIES_REPORT" >/dev/null 2>&1; then
  IMPORT_BOUNDARIES_STATUS="ERROR"
elif rg -n "R1 components->api/fetch" "$IMPORT_BOUNDARIES_REPORT" >/dev/null 2>&1; then
  IMPORT_BOUNDARIES_STATUS="FINDINGS"
else
  IMPORT_BOUNDARIES_STATUS="OK"
fi
echo "[END] frontend import boundaries"

echo "[START] frontend duplication"
{
  echo "# Frontend duplication audit"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v jscpd >/dev/null 2>&1; then
    run_with_timeout 90 jscpd "$FRONTEND_DIR/src" --silent --reporters console
    JSCPD_RC="$?"
    echo "jscpd_exit_code=$JSCPD_RC"
    [ "$JSCPD_RC" -eq 124 ] && echo "TIMEOUT"
  else
    echo "jscpd no instalado."
  fi
} >"$DUPLICATION_REPORT" 2>&1
run_with_timeout 60 sh -c "find \"$FRONTEND_DIR/src\" -type f \( -name '*Dialog*.tsx' -o -name '*Table*.tsx' -o -name '*Card*.tsx' -o -name '*Panel*.tsx' \) 2>/dev/null" >>"$DUPLICATION_REPORT" 2>&1
[ "$?" -eq 124 ] && echo "TIMEOUT fallback find/grep (60s)." >>"$DUPLICATION_REPORT"
append_timeout_note_if_needed "$DUPLICATION_REPORT"
if rg -n "TIMEOUT" "$DUPLICATION_REPORT" >/dev/null 2>&1; then
  DUPLICATION_STATUS="ERROR"
elif rg -n "jscpd no instalado" "$DUPLICATION_REPORT" >/dev/null 2>&1; then
  DUPLICATION_STATUS="NOT_INSTALLED"
else
  DUPLICATION_STATUS="FINDINGS"
fi
echo "[END] frontend duplication"

echo "[START] frontend dead code"
{
  echo "# Frontend dead code audit"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v ts-prune >/dev/null 2>&1; then
    run_with_timeout 90 sh -c "cd \"$FRONTEND_DIR\" && ts-prune"
    RC="$?"
    echo "ts_prune_exit_code=$RC"
    [ "$RC" -eq 124 ] && echo "TIMEOUT"
  elif command -v npx >/dev/null 2>&1; then
    run_with_timeout 90 sh -c "cd \"$FRONTEND_DIR\" && npx ts-prune"
    RC="$?"
    echo "npx_ts_prune_exit_code=$RC"
    [ "$RC" -eq 124 ] && echo "TIMEOUT"
  else
    echo "ts-prune no instalado y npx no disponible."
  fi
} >"$DEAD_CODE_REPORT" 2>&1
append_timeout_note_if_needed "$DEAD_CODE_REPORT"
if rg -n "TIMEOUT" "$DEAD_CODE_REPORT" >/dev/null 2>&1; then
  DEAD_CODE_STATUS="ERROR"
elif rg -n "no instalado|no disponible" "$DEAD_CODE_REPORT" >/dev/null 2>&1; then
  DEAD_CODE_STATUS="NOT_INSTALLED"
else
  DEAD_CODE_STATUS="FINDINGS"
fi
echo "[END] frontend dead code"

echo "[START] frontend solid/react"
SOLID_TMP="$RAW_DIR/.frontend_solid_react.py"
cat >"$SOLID_TMP" <<'PY'
import re
import sys
from datetime import datetime
smells, complexity, boundaries, dup, dead, out = sys.argv[1:7]
def read(p):
    try:
        return open(p, "r", encoding="utf-8").read()
    except Exception:
        return ""
s, c, b, d, dc = read(smells), read(complexity), read(boundaries), read(dup), read(dead)
large = len(re.findall(r"LARGE_FILE>300|> 300 líneas", s + "\n" + c))
hooks = len(re.findall(r"useEffect|react-hooks", s, re.IGNORECASE))
bound = len(re.findall(r"components->api|R1 ", b))
dup_signals = len(re.findall(r"Dialog|Table|Card|Panel", d))
dead_signals = len([ln for ln in dc.splitlines() if ln.strip() and ":" in ln and "node_modules" not in ln])
with open(out, "w", encoding="utf-8") as f:
    f.write("# Auditoría frontend - SOLID y patrones React\n\n")
    f.write("## Hallazgos iniciales\n\n")
    f.write(f"- Señales de componentes/archivos grandes: {large}\n")
    f.write(f"- Señales de imports sospechosos entre capas frontend: {bound}\n")
    f.write(f"- Señales de duplicación potencial: {dup_signals}\n")
    f.write(f"- Señales de código muerto potencial: {dead_signals}\n")
    f.write(f"- Señales de hooks/efectos a revisar: {hooks}\n\n")
    f.write("## Limitaciones\n\n")
    f.write("- Auditoría heurística con posibles falsos positivos.\n")
    f.write(f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
PY
run_with_timeout 60 python3 "$SOLID_TMP" "$CODE_SMELLS_REPORT" "$COMPLEXITY_REPORT" "$IMPORT_BOUNDARIES_REPORT" "$DUPLICATION_REPORT" "$DEAD_CODE_REPORT" "$SOLID_REACT_REPORT"
SR_RC="$?"
rm -f "$SOLID_TMP"
if [ "$SR_RC" -eq 124 ]; then
  {
    echo "# Auditoría frontend - SOLID y patrones React"
    echo
    echo "TIMEOUT"
  } >"$SOLID_REACT_REPORT"
  SOLID_REACT_STATUS="ERROR"
elif [ "$SR_RC" -eq 0 ]; then
  SOLID_REACT_STATUS="FINDINGS"
else
  SOLID_REACT_STATUS="ERROR"
fi
append_timeout_note_if_needed "$SOLID_REACT_REPORT"
echo "[END] frontend solid/react"

echo "Resumen frontend architecture audit:"
printf "%-24s | %-13s | %s\n" "Auditoria" "Estado" "Reporte"
printf "%-24s | %-13s | %s\n" "Code smells" "$CODE_SMELLS_STATUS" "audit/raw/frontend-code-smells.txt"
printf "%-24s | %-13s | %s\n" "Complejidad" "$COMPLEXITY_STATUS" "audit/raw/frontend-complexity.txt"
printf "%-24s | %-13s | %s\n" "Limites de imports" "$IMPORT_BOUNDARIES_STATUS" "audit/raw/frontend-import-boundaries.txt"
printf "%-24s | %-13s | %s\n" "Duplicacion" "$DUPLICATION_STATUS" "audit/raw/frontend-duplication.txt"
printf "%-24s | %-13s | %s\n" "Codigo muerto" "$DEAD_CODE_STATUS" "audit/raw/frontend-dead-code.txt"
printf "%-24s | %-13s | %s\n" "SOLID/React" "$SOLID_REACT_STATUS" "audit/raw/frontend-solid-react-audit.md"

exit 0
