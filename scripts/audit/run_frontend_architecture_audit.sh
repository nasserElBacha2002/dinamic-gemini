#!/usr/bin/env sh
set -u

echo "== Quality Gate - Frontend architecture audit (Fase 3.3) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"
mkdir -p "$RAW_DIR"

# Frontend path detection
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
  echo "Resumen frontend architecture audit:"
  printf "%-24s | %-13s | %s\n" "Auditoria" "Estado" "Reporte"
  printf "%-24s | %-13s | %s\n" "Code smells" "$CODE_SMELLS_STATUS" "audit/raw/frontend-code-smells.txt"
  printf "%-24s | %-13s | %s\n" "Complejidad" "$COMPLEXITY_STATUS" "audit/raw/frontend-complexity.txt"
  printf "%-24s | %-13s | %s\n" "Limites de imports" "$IMPORT_BOUNDARIES_STATUS" "audit/raw/frontend-import-boundaries.txt"
  printf "%-24s | %-13s | %s\n" "Duplicacion" "$DUPLICATION_STATUS" "audit/raw/frontend-duplication.txt"
  printf "%-24s | %-13s | %s\n" "Codigo muerto" "$DEAD_CODE_STATUS" "audit/raw/frontend-dead-code.txt"
  printf "%-24s | %-13s | %s\n" "SOLID/React" "$SOLID_REACT_STATUS" "audit/raw/frontend-solid-react-audit.md"
  exit 0
fi

# 1) Code smells
{
  echo "# Frontend code smells audit"
  echo "source_dir: $FRONTEND_DIR"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v npm >/dev/null 2>&1 && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "## ESLint"
    (cd "$FRONTEND_DIR" && npm run lint)
    eslint_exit="$?"
    echo
    echo "eslint_exit_code=$eslint_exit"
  else
    echo "ESLint no disponible (npm o package.json faltante)."
    eslint_exit=127
  fi

  if [ -f "$FRONTEND_DIR/package.json" ]; then
    echo
    echo "## Heurísticas de smells (fallback textual)"
    find "$FRONTEND_DIR/src" -type f \( -name "*.tsx" -o -name "*.ts" \) \
      ! -path "*/node_modules/*" ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/coverage/*" ! -path "*/.vite/*" \
      -print0 2>/dev/null | while IFS= read -r -d '' f; do
        lines="$(wc -l <"$f" | tr -d ' ')"
        [ "$lines" -gt 300 ] && echo "LARGE_FILE>300: ${f#$FRONTEND_DIR/} ($lines)"
      done
    find "$FRONTEND_DIR/src" -type f \( -name "*.tsx" -o -name "*.ts" \) \
      ! -path "*/node_modules/*" ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/coverage/*" ! -path "*/.vite/*" \
      -print0 2>/dev/null | xargs -0 grep -nE "useEffect\s*\(" 2>/dev/null | wc -l | awk '{print "useEffect_usages_approx=" $1}'
  fi
} >"$CODE_SMELLS_REPORT" 2>&1
if rg -n "eslint_exit_code=127|ESLint no disponible" "$CODE_SMELLS_REPORT" >/dev/null 2>&1; then
  CODE_SMELLS_STATUS="NOT_INSTALLED"
elif rg -n "eslint_exit_code=0" "$CODE_SMELLS_REPORT" >/dev/null 2>&1; then
  CODE_SMELLS_STATUS="OK"
else
  CODE_SMELLS_STATUS="FINDINGS"
fi

# 2) Complexity
python3 - "$FRONTEND_DIR" "$COMPLEXITY_REPORT" <<'PY'
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
high_conditional = []

for f in files:
    try:
        txt = open(f, "r", encoding="utf-8").read()
    except Exception:
        continue
    lines = txt.splitlines()
    rel = f.replace(root + os.sep, "").replace("\\", "/")
    n_lines = len(lines)
    n_funcs = len(re.findall(r"\bfunction\b|=>", txt))
    n_if = len(re.findall(r"\bif\s*\(", txt))
    n_for = len(re.findall(r"\bfor\s*\(", txt))
    n_switch = len(re.findall(r"\bswitch\s*\(", txt))
    cond_score = n_if + n_for + n_switch
    summary["files"] += 1
    summary["functions"] += n_funcs
    summary["if_for_switch"] += cond_score
    if n_lines > 300:
        large_files.append((rel, n_lines))
    if cond_score > 25:
        high_conditional.append((rel, cond_score, n_lines))

with open(report, "w", encoding="utf-8") as out:
    out.write("# Frontend complexity audit\n")
    out.write(f"generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    out.write("## Resumen\n")
    out.write(f"- files_scanned: {summary['files']}\n")
    out.write(f"- functions_approx: {summary['functions']}\n")
    out.write(f"- conditional_tokens_approx: {summary['if_for_switch']}\n\n")
    out.write("## Clasificación\n")
    out.write("- A/B: aceptable\n")
    out.write("- C: revisar\n")
    out.write("- D/E/F: alto riesgo\n\n")
    out.write("## Archivos > 300 líneas (revisar)\n")
    if not large_files:
        out.write("- No detectados.\n")
    else:
        for rel, ln in sorted(large_files, key=lambda x: x[1], reverse=True)[:80]:
            out.write(f"- {rel}: {ln}\n")
    out.write("\n## Archivos con alta densidad condicional (riesgo)\n")
    if not high_conditional:
        out.write("- No detectados.\n")
    else:
        for rel, c, ln in sorted(high_conditional, key=lambda x: x[1], reverse=True)[:80]:
            out.write(f"- {rel}: cond={c}, lines={ln}\n")
    out.write("\nObservación: auditoría heurística por conteo textual.\n")
PY
if [ "$?" -eq 0 ]; then
  COMPLEXITY_STATUS="FINDINGS"
else
  COMPLEXITY_STATUS="ERROR"
fi

# 3) Import boundaries (madge/depcruise optional + fallback)
{
  echo "# Frontend import boundaries audit"
  echo "source_dir: $FRONTEND_DIR/src"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  echo "## Tool checks"
  if command -v madge >/dev/null 2>&1; then
    echo "- madge: installed"
    (cd "$FRONTEND_DIR" && madge --circular src) || true
  else
    echo "- madge: not installed"
  fi
  if command -v depcruise >/dev/null 2>&1; then
    echo "- dependency-cruiser: installed"
  else
    echo "- dependency-cruiser: not installed"
  fi
  echo
  echo "## Heurística de imports sospechosos"
  find "$FRONTEND_DIR/src/components" -type f \( -name "*.tsx" -o -name "*.ts" \) 2>/dev/null | while IFS= read -r f; do
    grep -nE "from ['\"](\.\./)*api/|from ['\"]@/api/|axios|fetch\(" "$f" >/dev/null 2>&1 && \
      echo "R1 components->api/fetch: ${f#$FRONTEND_DIR/}"
  done
  find "$FRONTEND_DIR/src/features" -type f \( -name "*.tsx" -o -name "*.ts" \) 2>/dev/null | while IFS= read -r f; do
    grep -nE "from ['\"](\.\./)*features/" "$f" >/dev/null 2>&1 && \
      echo "R3 feature cross-import: ${f#$FRONTEND_DIR/}"
  done
  find "$FRONTEND_DIR/src/components" -type f \( -name "*.tsx" -o -name "*.ts" \) 2>/dev/null | while IFS= read -r f; do
    grep -nE "switch\s*\(|if\s*\(" "$f" >/dev/null 2>&1 && \
      echo "R4 ui-business-logic-suspect: ${f#$FRONTEND_DIR/}"
  done
  echo
  echo "Reglas auditadas:"
  echo "- R1 components no deberían importar API concreta ni usar fetch/axios directo."
  echo "- R2 hooks como capa intermedia de lógica."
  echo "- R3 features evitar acoplamiento circular/cruzado innecesario."
  echo "- R4 UI evitar lógica de negocio pesada."
} >"$IMPORT_BOUNDARIES_REPORT" 2>&1
if rg -n "suspect|cross-import|components->api" "$IMPORT_BOUNDARIES_REPORT" >/dev/null 2>&1; then
  IMPORT_BOUNDARIES_STATUS="FINDINGS"
else
  IMPORT_BOUNDARIES_STATUS="OK"
fi

# 4) Duplication
{
  echo "# Frontend duplication audit"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v jscpd >/dev/null 2>&1; then
    echo "## jscpd"
    jscpd "$FRONTEND_DIR/src" --silent --reporters console
    echo "jscpd_exit_code=$?"
  else
    echo "jscpd no instalado. Usando fallback heurístico."
    echo
    echo "## Fallback heurístico"
    echo "- Buscando archivos con nombres de componentes repetidos por sufijo."
    find "$FRONTEND_DIR/src" -type f \( -name "*Dialog*.tsx" -o -name "*Table*.tsx" -o -name "*Card*.tsx" -o -name "*Panel*.tsx" \) \
      ! -path "*/node_modules/*" ! -path "*/dist/*" ! -path "*/build/*" ! -path "*/coverage/*" ! -path "*/.vite/*" 2>/dev/null | sed "s|$FRONTEND_DIR/|- |"
  fi
} >"$DUPLICATION_REPORT" 2>&1
if rg -n "jscpd no instalado" "$DUPLICATION_REPORT" >/dev/null 2>&1; then
  DUPLICATION_STATUS="NOT_INSTALLED"
else
  DUPLICATION_STATUS="FINDINGS"
fi

# 5) Dead code
{
  echo "# Frontend dead code audit"
  echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  if command -v ts-prune >/dev/null 2>&1; then
    echo "## ts-prune"
    (cd "$FRONTEND_DIR" && ts-prune)
    echo "ts_prune_exit_code=$?"
  elif command -v npx >/dev/null 2>&1; then
    echo "## npx ts-prune fallback"
    (cd "$FRONTEND_DIR" && npx ts-prune)
    echo "npx_ts_prune_exit_code=$?"
  else
    echo "ts-prune no instalado y npx no disponible."
    echo
    echo "## Fallback heurístico"
    echo "- No se pudo ejecutar detección de exports no usados en forma automática."
  fi
} >"$DEAD_CODE_REPORT" 2>&1
if rg -n "no instalado|No se pudo ejecutar" "$DEAD_CODE_REPORT" >/dev/null 2>&1; then
  DEAD_CODE_STATUS="NOT_INSTALLED"
else
  DEAD_CODE_STATUS="FINDINGS"
fi

# 6) SOLID + React report synthesis
python3 - "$CODE_SMELLS_REPORT" "$COMPLEXITY_REPORT" "$IMPORT_BOUNDARIES_REPORT" "$DUPLICATION_REPORT" "$DEAD_CODE_REPORT" "$SOLID_REACT_REPORT" <<'PY'
import re
import sys
from datetime import datetime

smells, complexity, boundaries, dup, dead, out = sys.argv[1:7]

def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

s = read(smells)
c = read(complexity)
b = read(boundaries)
d = read(dup)
dc = read(dead)

large_components = len(re.findall(r"LARGE_FILE>300", s)) + len(re.findall(r"> 300 líneas", c))
hook_findings = len(re.findall(r"useEffect|react-hooks", s, re.IGNORECASE))
boundary_findings = len(re.findall(r"suspect|cross-import|components->api", b))
dup_signals = len(re.findall(r"Dialog|Table|Card|Panel", d))
dead_signals = len([ln for ln in dc.splitlines() if ln.strip() and ":" in ln and "node_modules" not in ln])

with open(out, "w", encoding="utf-8") as f:
    f.write("# Auditoría frontend - SOLID y patrones React\n\n")
    f.write("## Alcance\n\n")
    f.write("Evaluación heurística de arquitectura frontend (React + TypeScript + Vite), sin cambios funcionales.\n\n")
    f.write("## Señales automáticas analizadas\n\n")
    f.write(f"- tamaño de componentes: señales={large_components}\n")
    f.write("- complejidad: basada en líneas/funciones/condicionales por archivo\n")
    f.write(f"- duplicación: señales={dup_signals}\n")
    f.write(f"- imports entre capas: señales={boundary_findings}\n")
    f.write(f"- hooks y efectos: señales={hook_findings}\n")
    f.write(f"- código muerto potencial: señales={dead_signals}\n\n")

    f.write("## SOLID aplicado a frontend\n\n")
    f.write("### Single Responsibility\n")
    f.write("- Señales: componentes con mezcla de UI + fetch + navegación + estado complejo.\n\n")
    f.write("### Open/Closed\n")
    f.write("- Señales: `if/switch` extensos en render para status/tipo/provider.\n\n")
    f.write("### Liskov\n")
    f.write("- Señales: props inconsistentes en componentes reutilizables o contratos ambiguos.\n\n")
    f.write("### Interface Segregation\n")
    f.write("- Señales: interfaces de props grandes y hooks con retornos demasiado amplios.\n\n")
    f.write("### Dependency Inversion\n")
    f.write("- Señales: UI importando servicios concretos en lugar de capa de hooks/adapters.\n\n")

    f.write("## Patrones React\n\n")
    f.write("- uso de hooks: revisar efectos con lógica no trivial.\n")
    f.write("- separación UI vs lógica: fortalecer composición y hooks intermedios.\n")
    f.write("- TanStack Query vs fetch manual: evaluar consistencia por feature.\n")
    f.write("- manejo de estado: controlar crecimiento de estado local en componentes grandes.\n")
    f.write("- composición de componentes: detectar sobreacoplamiento entre features.\n\n")

    f.write("## Hallazgos iniciales\n\n")
    f.write(f"- Señales de componentes/archivos grandes: {large_components}\n")
    f.write(f"- Señales de imports sospechosos entre capas frontend: {boundary_findings}\n")
    f.write(f"- Señales de duplicación potencial: {dup_signals}\n")
    f.write(f"- Señales de código muerto potencial: {dead_signals}\n")
    f.write(f"- Señales de hooks/efectos a revisar: {hook_findings}\n\n")

    f.write("## Limitaciones\n\n")
    f.write("- Auditoría heurística y no determinista en términos arquitectónicos.\n")
    f.write("- Puede producir falsos positivos/falsos negativos.\n")
    f.write("- Requiere validación manual por módulo/feature.\n\n")

    f.write("## Recomendaciones futuras\n\n")
    f.write("- Definir contratos claros UI/hooks/services por feature.\n")
    f.write("- Introducir reglas de arquitectura frontend versionadas (import boundaries).\n")
    f.write("- Priorizar remediación incremental por riesgo (hooks críticos, coupling, duplicación).\n")
    f.write(f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
PY
if [ "$?" -eq 0 ]; then
  SOLID_REACT_STATUS="FINDINGS"
else
  SOLID_REACT_STATUS="ERROR"
fi

echo "Resumen frontend architecture audit:"
printf "%-24s | %-13s | %s\n" "Auditoria" "Estado" "Reporte"
printf "%-24s | %-13s | %s\n" "Code smells" "$CODE_SMELLS_STATUS" "audit/raw/frontend-code-smells.txt"
printf "%-24s | %-13s | %s\n" "Complejidad" "$COMPLEXITY_STATUS" "audit/raw/frontend-complexity.txt"
printf "%-24s | %-13s | %s\n" "Limites de imports" "$IMPORT_BOUNDARIES_STATUS" "audit/raw/frontend-import-boundaries.txt"
printf "%-24s | %-13s | %s\n" "Duplicacion" "$DUPLICATION_STATUS" "audit/raw/frontend-duplication.txt"
printf "%-24s | %-13s | %s\n" "Codigo muerto" "$DEAD_CODE_STATUS" "audit/raw/frontend-dead-code.txt"
printf "%-24s | %-13s | %s\n" "SOLID/React" "$SOLID_REACT_STATUS" "audit/raw/frontend-solid-react-audit.md"

exit 0
