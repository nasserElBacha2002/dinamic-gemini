#!/usr/bin/env sh
set -u

echo "== Quality Gate - Frontend audit (Fase 3) =="

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

ESLINT_REPORT="$RAW_DIR/frontend-eslint.txt"
TYPECHECK_REPORT="$RAW_DIR/frontend-typecheck.txt"
NPM_AUDIT_REPORT="$RAW_DIR/frontend-npm-audit.json"
VITEST_REPORT="$RAW_DIR/frontend-vitest.txt"
USEEFFECT_AUDIT_REPORT="$RAW_DIR/frontend-useeffects-audit.md"
ERROR_HANDLING_AUDIT_REPORT="$RAW_DIR/frontend-error-handling-audit.md"
REUSABLE_AUDIT_REPORT="$RAW_DIR/frontend-reusable-components-audit.md"

ESLINT_STATUS="SKIPPED"
TYPECHECK_STATUS="SKIPPED"
NPM_AUDIT_STATUS="SKIPPED"
VITEST_STATUS="SKIPPED"
USEEFFECT_STATUS="SKIPPED"
ERROR_HANDLING_STATUS="SKIPPED"
REUSABLE_STATUS="SKIPPED"

write_note() {
  report_path="$1"
  message="$2"
  {
    echo "$message"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  } >"$report_path"
}

mark_from_exit_code() {
  exit_code="$1"
  if [ "$exit_code" -eq 0 ]; then
    echo "OK"
  elif [ "$exit_code" -eq 1 ]; then
    echo "FINDINGS"
  else
    echo "ERROR"
  fi
}

has_script() {
  script_name="$1"
  node -e "const fs=require('fs');const p=process.argv[1];const n=process.argv[2];const j=JSON.parse(fs.readFileSync(p,'utf8'));process.exit(j.scripts&&Object.prototype.hasOwnProperty.call(j.scripts,n)?0:1);" \
    "$FRONTEND_DIR/package.json" "$script_name" >/dev/null 2>&1
}

rg_count() {
  pattern="$1"
  if command -v rg >/dev/null 2>&1; then
    rg -n --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!coverage/**' --glob '!.vite/**' \
      -g '**/*.ts' -g '**/*.tsx' "$pattern" "$FRONTEND_DIR" 2>/dev/null | wc -l | tr -d ' '
  else
    find "$FRONTEND_DIR" -type f \( -name '*.ts' -o -name '*.tsx' \) \
      ! -path '*/node_modules/*' ! -path '*/dist/*' ! -path '*/build/*' ! -path '*/coverage/*' ! -path '*/.vite/*' \
      -print0 2>/dev/null | xargs -0 grep -nE "$pattern" 2>/dev/null | wc -l | tr -d ' '
  fi
}

rg_files() {
  pattern="$1"
  if command -v rg >/dev/null 2>&1; then
    rg --files-with-matches --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!coverage/**' --glob '!.vite/**' \
      -g '**/*.ts' -g '**/*.tsx' "$pattern" "$FRONTEND_DIR" 2>/dev/null | sed "s|$FRONTEND_DIR/||"
  else
    find "$FRONTEND_DIR" -type f \( -name '*.ts' -o -name '*.tsx' \) \
      ! -path '*/node_modules/*' ! -path '*/dist/*' ! -path '*/build/*' ! -path '*/coverage/*' ! -path '*/.vite/*' \
      -print0 2>/dev/null | xargs -0 grep -lE "$pattern" 2>/dev/null | sed "s|$FRONTEND_DIR/||"
  fi
}

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio frontend detectado: ${FRONTEND_DIR:-NO_ENCONTRADO}"
echo "Directorio de evidencia: $RAW_DIR"
echo

# ESLint
if [ -z "$FRONTEND_DIR" ] || [ ! -f "$FRONTEND_DIR/package.json" ]; then
  ESLINT_STATUS="SKIPPED"
  write_note "$ESLINT_REPORT" "ESLint no ejecutado: no se detecto frontend/package.json."
elif ! command -v npm >/dev/null 2>&1; then
  ESLINT_STATUS="NOT_INSTALLED"
  write_note "$ESLINT_REPORT" "npm no esta instalado en el entorno actual."
elif has_script "lint"; then
  (cd "$FRONTEND_DIR" && npm run lint) >"$ESLINT_REPORT" 2>&1
  ESLINT_STATUS="$(mark_from_exit_code "$?")"
else
  ESLINT_STATUS="SKIPPED"
  write_note "$ESLINT_REPORT" "ESLint no ejecutado: no se encontro script 'lint' en package.json."
fi

# Typecheck
if [ -z "$FRONTEND_DIR" ] || [ ! -f "$FRONTEND_DIR/package.json" ]; then
  TYPECHECK_STATUS="SKIPPED"
  write_note "$TYPECHECK_REPORT" "Typecheck no ejecutado: no se detecto frontend/package.json."
elif ! command -v npm >/dev/null 2>&1; then
  TYPECHECK_STATUS="NOT_INSTALLED"
  write_note "$TYPECHECK_REPORT" "npm no esta instalado en el entorno actual."
elif has_script "typecheck"; then
  (cd "$FRONTEND_DIR" && npm run typecheck) >"$TYPECHECK_REPORT" 2>&1
  TYPECHECK_STATUS="$(mark_from_exit_code "$?")"
elif command -v npx >/dev/null 2>&1; then
  (cd "$FRONTEND_DIR" && npx tsc --noEmit) >"$TYPECHECK_REPORT" 2>&1
  TYPECHECK_STATUS="$(mark_from_exit_code "$?")"
else
  TYPECHECK_STATUS="NOT_INSTALLED"
  write_note "$TYPECHECK_REPORT" "Typecheck no ejecutado: no hay script 'typecheck' y npx no esta disponible."
fi

# npm audit
if [ -z "$FRONTEND_DIR" ] || [ ! -f "$FRONTEND_DIR/package.json" ]; then
  NPM_AUDIT_STATUS="SKIPPED"
  write_note "$NPM_AUDIT_REPORT" "npm audit no ejecutado: no se detecto frontend/package.json."
elif ! command -v npm >/dev/null 2>&1; then
  NPM_AUDIT_STATUS="NOT_INSTALLED"
  write_note "$NPM_AUDIT_REPORT" "npm no esta instalado en el entorno actual."
else
  (cd "$FRONTEND_DIR" && npm audit --json) >"$NPM_AUDIT_REPORT" 2>&1
  audit_exit="$?"
  if [ "$audit_exit" -eq 0 ]; then
    NPM_AUDIT_STATUS="OK"
  elif [ "$audit_exit" -eq 1 ]; then
    NPM_AUDIT_STATUS="FINDINGS"
  else
    NPM_AUDIT_STATUS="ERROR"
  fi
fi

# Vitest
if [ -z "$FRONTEND_DIR" ] || [ ! -f "$FRONTEND_DIR/package.json" ]; then
  VITEST_STATUS="SKIPPED"
  write_note "$VITEST_REPORT" "Vitest no ejecutado: no se detecto frontend/package.json."
elif ! command -v npm >/dev/null 2>&1; then
  VITEST_STATUS="NOT_INSTALLED"
  write_note "$VITEST_REPORT" "npm no esta instalado en el entorno actual."
elif has_script "test"; then
  (cd "$FRONTEND_DIR" && npm run test -- --run) >"$VITEST_REPORT" 2>&1
  VITEST_STATUS="$(mark_from_exit_code "$?")"
else
  VITEST_STATUS="SKIPPED"
  write_note "$VITEST_REPORT" "Vitest no ejecutado: no se encontro script 'test' en package.json."
fi

# Static audits
if [ -z "$FRONTEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
  USEEFFECT_STATUS="SKIPPED"
  ERROR_HANDLING_STATUS="SKIPPED"
  REUSABLE_STATUS="SKIPPED"
  write_note "$USEEFFECT_AUDIT_REPORT" "Auditoria useEffect no ejecutada: frontend no detectado."
  write_note "$ERROR_HANDLING_AUDIT_REPORT" "Auditoria de manejo de errores no ejecutada: frontend no detectado."
  write_note "$REUSABLE_AUDIT_REPORT" "Auditoria de componentes reutilizables no ejecutada: frontend no detectado."
elif ! command -v rg >/dev/null 2>&1; then
  echo "Aviso: rg no esta disponible; se usa fallback con find/grep para auditorias estaticas."
fi

if [ -n "$FRONTEND_DIR" ] && [ -d "$FRONTEND_DIR" ]; then
  USEEFFECT_COUNT="$(rg_count 'useEffect\s*\(')"
  USEEFFECT_FILES="$(rg_files 'useEffect\s*\(')"
  USEEFFECT_NO_DEPS="$(rg_count 'useEffect\s*\([^,]*\)')"
  USEEFFECT_EMPTY_DEPS="$(rg_count 'useEffect\s*\([^)]*,\s*\[\s*\]\s*\)')"
  USEEFFECT_FETCH="$(rg_count 'useEffect[\s\S]{0,600}fetch\s*\(')"
  USEEFFECT_INTERVAL="$(rg_count 'useEffect[\s\S]{0,600}setInterval\s*\(|useEffect[\s\S]{0,600}setTimeout\s*\(')"
  USEEFFECT_LISTENER="$(rg_count 'useEffect[\s\S]{0,600}addEventListener\s*\(')"
  USEEFFECT_CONSOLE_ERROR="$(rg_count 'useEffect[\s\S]{0,600}console\.error')"
  USEEFFECT_QUERY_RISK="$(rg_count 'useEffect[\s\S]{0,800}(fetch\s*\(|axios\.|api\.|/api/)')"

  {
    echo "# Auditoría frontend - useEffect"
    echo
    echo "## Resumen"
    echo
    echo "- Cantidad aproximada de usos de \`useEffect\`: $USEEFFECT_COUNT"
    echo "- Cantidad aproximada de archivos con \`useEffect\`: $(printf '%s\n' "$USEEFFECT_FILES" | awk 'NF{c++} END{print c+0}')"
    echo
    echo "## Archivos detectados"
    echo
    if [ -n "$USEEFFECT_FILES" ]; then
      printf '%s\n' "$USEEFFECT_FILES" | sed 's/^/- /'
    else
      echo "- No se detectaron archivos con useEffect."
    fi
    echo
    echo "## Patrones a revisar"
    echo
    echo "- useEffect sin dependency array (aprox): $USEEFFECT_NO_DEPS"
    echo "- useEffect con dependency array vacio [] (aprox): $USEEFFECT_EMPTY_DEPS"
    echo "- useEffect con fetch (aprox): $USEEFFECT_FETCH"
    echo "- useEffect con setInterval/setTimeout (aprox): $USEEFFECT_INTERVAL"
    echo "- useEffect con addEventListener (aprox): $USEEFFECT_LISTENER"
    echo "- useEffect con console.error (aprox): $USEEFFECT_CONSOLE_ERROR"
    echo "- useEffect con posible logica de API movible a TanStack Query (aprox): $USEEFFECT_QUERY_RISK"
    echo
    echo "## Recomendaciones futuras"
    echo
    echo "- Revisar useEffect sin dependencias declaradas para evitar efectos no deterministas."
    echo "- Evaluar migracion de fetching manual a hooks de TanStack Query donde aplique."
    echo "- Confirmar limpieza de listeners y timers en efectos con recursos persistentes."
    echo "- Validar manualmente los conteos aproximados; este reporte usa heuristicas por patron de texto."
  } >"$USEEFFECT_AUDIT_REPORT"
  USEEFFECT_STATUS="FINDINGS"

  ERROR_FILES="$(rg_files 'catch\s*\(|\.catch\s*\(|console\.error|throw new Error|onError|isError|error|try\s*\{')"
  CATCH_EMPTY="$(rg_count 'catch\s*\([^)]*\)\s*\{\s*\}')"
  CATCH_LOG_ONLY="$(rg_count 'catch\s*\([^)]*\)\s*\{[\s\S]{0,240}console\.error[\s\S]{0,240}\}')"
  TRY_COUNT="$(rg_count 'try\s*\{')"
  CATCH_COUNT="$(rg_count 'catch\s*\(')"
  ONERROR_COUNT="$(rg_count 'onError')"
  ISERROR_COUNT="$(rg_count 'isError')"
  THROW_ERROR_COUNT="$(rg_count 'throw new Error')"

  {
    echo "# Auditoría frontend - manejo de errores"
    echo
    echo "## Resumen"
    echo
    echo "- Archivos con patrones de manejo de errores detectados (aprox): $(printf '%s\n' "$ERROR_FILES" | awk 'NF{c++} END{print c+0}')"
    echo "- Bloques try detectados (aprox): $TRY_COUNT"
    echo "- Bloques catch detectados (aprox): $CATCH_COUNT"
    echo
    echo "## Archivos detectados"
    echo
    if [ -n "$ERROR_FILES" ]; then
      printf '%s\n' "$ERROR_FILES" | sed 's/^/- /'
    else
      echo "- No se detectaron archivos con patrones de manejo de errores."
    fi
    echo
    echo "## Patrones encontrados"
    echo
    echo "- catch vacio (aprox): $CATCH_EMPTY"
    echo "- catch con solo console.error (aprox): $CATCH_LOG_ONLY"
    echo "- uso de onError (aprox): $ONERROR_COUNT"
    echo "- uso de isError (aprox): $ISERROR_COUNT"
    echo "- throw new Error (aprox): $THROW_ERROR_COUNT"
    echo
    echo "## Riesgos a revisar"
    echo
    echo "- Bloques catch que no escalan ni muestran feedback al usuario."
    echo "- Errores solo logueados en consola sin estrategia de UX de error."
    echo "- Flujos de query/mutation sin manejo explicito de estados de error."
    echo "- Mensajes tecnicos potencialmente expuestos de forma directa en UI."
    echo
    echo "## Recomendaciones futuras"
    echo
    echo "- Definir un patron comun de error UI (toast/alerta/estado en pantalla)."
    echo "- Estandarizar manejo de errores en hooks de datos con TanStack Query."
    echo "- Revisar manualmente resultados: el analisis actual es estatico por patrones de texto."
  } >"$ERROR_HANDLING_AUDIT_REPORT"
  ERROR_HANDLING_STATUS="FINDINGS"

  if command -v rg >/dev/null 2>&1; then
    COMPONENT_FILES="$(rg --files --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!coverage/**' --glob '!.vite/**' \
      "$FRONTEND_DIR/src/components/**" "$FRONTEND_DIR/src/pages/**" "$FRONTEND_DIR/src/views/**" "$FRONTEND_DIR/src/features/**" 2>/dev/null | sed "s|$FRONTEND_DIR/||")"
  else
    COMPONENT_FILES="$(find "$FRONTEND_DIR/src" -type f \( -name '*.ts' -o -name '*.tsx' \) \
      \( -path "$FRONTEND_DIR/src/components/*" -o -path "$FRONTEND_DIR/src/pages/*" -o -path "$FRONTEND_DIR/src/views/*" -o -path "$FRONTEND_DIR/src/features/*" \) 2>/dev/null | sed "s|$FRONTEND_DIR/||")"
  fi
  BTN_COUNT="$(rg_count 'Button')"
  CARD_COUNT="$(rg_count 'Card')"
  DIALOG_COUNT="$(rg_count 'Dialog|Modal')"
  TABLE_COUNT="$(rg_count 'Table|DataGrid')"
  TEXTFIELD_COUNT="$(rg_count 'TextField')"
  LOADING_COUNT="$(rg_count 'CircularProgress|Loading|Skeleton')"
  ALERT_COUNT="$(rg_count 'Alert|Snackbar|ErrorState|Empty')"

  {
    echo "# Auditoría frontend - componentes reutilizables"
    echo
    echo "## Resumen"
    echo
    echo "- Archivos en zonas candidatas a reutilizacion (components/pages/views/features): $(printf '%s\n' "$COMPONENT_FILES" | awk 'NF{c++} END{print c+0}')"
    echo "- El objetivo es detectar repeticion visual o de logica para consolidar componentes."
    echo
    echo "## Componentes detectados"
    echo
    echo "- Referencias a Button: $BTN_COUNT"
    echo "- Referencias a Card: $CARD_COUNT"
    echo "- Referencias a Dialog/Modal: $DIALOG_COUNT"
    echo "- Referencias a Table/DataGrid: $TABLE_COUNT"
    echo "- Referencias a TextField: $TEXTFIELD_COUNT"
    echo "- Referencias a Loading/CircularProgress: $LOADING_COUNT"
    echo "- Referencias a Alert/Snackbar/ErrorState/Empty: $ALERT_COUNT"
    echo
    echo "## Patrones repetidos a revisar"
    echo
    echo "- Construcciones repetidas de tablas y filtros en modulos de resultados/revision."
    echo "- Dialogs con estructura similar que podrian compartir base comun."
    echo "- Estados de loading/empty/error potencialmente dispersos en multiples pantallas."
    echo
    echo "## Posibles candidatos a componente genérico"
    echo
    echo "- Contenedores de estado de datos: loading/empty/error."
    echo "- Dialogs base con layout, acciones y comportamiento estandar."
    echo "- Toolbars de filtros y tablas con paginacion/orden reutilizables."
    echo
    echo "## Recomendaciones futuras"
    echo
    echo "- Crear inventario de componentes por dominio antes de consolidar."
    echo "- Definir criterios de extraccion (repeticion, acoplamiento, estabilidad)."
    echo "- Validar manualmente hallazgos; este reporte usa conteo por patrones de texto."
  } >"$REUSABLE_AUDIT_REPORT"
  REUSABLE_STATUS="FINDINGS"
fi

echo "Resumen frontend audit:"
printf "%-32s | %-13s | %s\n" "Herramienta" "Estado" "Reporte"
printf "%-32s | %-13s | %s\n" "ESLint" "$ESLINT_STATUS" "audit/raw/frontend-eslint.txt"
printf "%-32s | %-13s | %s\n" "Typecheck" "$TYPECHECK_STATUS" "audit/raw/frontend-typecheck.txt"
printf "%-32s | %-13s | %s\n" "npm audit" "$NPM_AUDIT_STATUS" "audit/raw/frontend-npm-audit.json"
printf "%-32s | %-13s | %s\n" "Vitest" "$VITEST_STATUS" "audit/raw/frontend-vitest.txt"
printf "%-32s | %-13s | %s\n" "useEffect audit" "$USEEFFECT_STATUS" "audit/raw/frontend-useeffects-audit.md"
printf "%-32s | %-13s | %s\n" "Error handling audit" "$ERROR_HANDLING_STATUS" "audit/raw/frontend-error-handling-audit.md"
printf "%-32s | %-13s | %s\n" "Reusable components audit" "$REUSABLE_STATUS" "audit/raw/frontend-reusable-components-audit.md"

exit 0
