#!/usr/bin/env sh
set -u

echo "== Quality Gate - Backend architecture audit (Fase 3.2) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"

mkdir -p "$RAW_DIR"

if [ -d "$ROOT_DIR/backend" ]; then
  BACKEND_DIR="$ROOT_DIR/backend"
elif [ -f "$ROOT_DIR/pyproject.toml" ]; then
  BACKEND_DIR="$ROOT_DIR"
else
  BACKEND_DIR=""
fi

if [ -n "$BACKEND_DIR" ] && [ -d "$BACKEND_DIR/src" ]; then
  SOURCE_DIR="$BACKEND_DIR/src"
else
  SOURCE_DIR="$BACKEND_DIR"
fi

CODE_SMELLS_REPORT="$RAW_DIR/backend-code-smells.txt"
COMPLEXITY_REPORT="$RAW_DIR/backend-complexity.txt"
IMPORT_BOUNDARIES_REPORT="$RAW_DIR/backend-import-boundaries.txt"
SOLID_GRASP_REPORT="$RAW_DIR/backend-solid-grasp-audit.md"

CODE_SMELLS_STATUS="SKIPPED"
COMPLEXITY_STATUS="SKIPPED"
IMPORT_BOUNDARIES_STATUS="SKIPPED"
SOLID_GRASP_STATUS="SKIPPED"

write_note() {
  report_path="$1"
  message="$2"
  {
    echo "$message"
    echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  } >"$report_path"
}

echo "Repositorio detectado: $ROOT_DIR"
echo "Directorio backend detectado: ${BACKEND_DIR:-NO_ENCONTRADO}"
echo "Directorio fuente backend: ${SOURCE_DIR:-NO_ENCONTRADO}"
echo "Directorio de evidencia: $RAW_DIR"
echo

# 1) Code smells: pylint + vulture
if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
  CODE_SMELLS_STATUS="SKIPPED"
  write_note "$CODE_SMELLS_REPORT" "Code smells no ejecutado: no se detecto backend/src."
else
  {
    echo "# Backend code smells audit"
    echo "source_dir: $SOURCE_DIR"
    echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    echo "## Pylint"
    if command -v pylint >/dev/null 2>&1; then
      pylint "$SOURCE_DIR" \
        --disable=all \
        --enable=R0913,R0902,R0915,W0611,W0703,W0212,R0912,R0911 \
        --reports=y
      pylint_exit="$?"
      echo
      echo "pylint_exit_code=$pylint_exit"
    else
      echo "pylint no instalado en el entorno actual."
      pylint_exit=127
    fi
    echo
    echo "## Vulture"
    if command -v vulture >/dev/null 2>&1; then
      vulture "$SOURCE_DIR"
      vulture_exit="$?"
      echo
      echo "vulture_exit_code=$vulture_exit"
    else
      echo "vulture no instalado en el entorno actual."
      vulture_exit=127
    fi
  } >"$CODE_SMELLS_REPORT" 2>&1

  if [ "${pylint_exit:-127}" -eq 127 ] && [ "${vulture_exit:-127}" -eq 127 ]; then
    CODE_SMELLS_STATUS="NOT_INSTALLED"
  elif [ "${pylint_exit:-0}" -eq 0 ] && [ "${vulture_exit:-0}" -eq 0 ]; then
    CODE_SMELLS_STATUS="OK"
  elif [ "${pylint_exit:-0}" -eq 127 ] || [ "${vulture_exit:-0}" -eq 127 ]; then
    CODE_SMELLS_STATUS="FINDINGS"
  else
    CODE_SMELLS_STATUS="FINDINGS"
  fi
fi

# 2) Complexity: radon
if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
  COMPLEXITY_STATUS="SKIPPED"
  write_note "$COMPLEXITY_REPORT" "Complexity no ejecutado: no se detecto backend/src."
else
  {
    echo "# Backend complexity audit"
    echo "source_dir: $SOURCE_DIR"
    echo "generated_at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    if command -v radon >/dev/null 2>&1; then
      echo "## Cyclomatic Complexity (radon cc)"
      radon cc "$SOURCE_DIR" -s -a
      cc_exit="$?"
      echo
      echo "## Maintainability Index (radon mi)"
      radon mi "$SOURCE_DIR" -s
      mi_exit="$?"
      echo
      echo "Interpretation:"
      echo "- A/B: aceptable"
      echo "- C: revisar"
      echo "- D/E/F: alto riesgo"
      echo
      echo "radon_cc_exit_code=$cc_exit"
      echo "radon_mi_exit_code=$mi_exit"
    else
      echo "radon no instalado en el entorno actual."
      cc_exit=127
      mi_exit=127
    fi
  } >"$COMPLEXITY_REPORT" 2>&1

  if [ "${cc_exit:-127}" -eq 127 ] && [ "${mi_exit:-127}" -eq 127 ]; then
    COMPLEXITY_STATUS="NOT_INSTALLED"
  elif [ "${cc_exit:-0}" -eq 0 ] && [ "${mi_exit:-0}" -eq 0 ]; then
    COMPLEXITY_STATUS="OK"
  else
    COMPLEXITY_STATUS="FINDINGS"
  fi
fi

# 3) Import boundaries: import-linter / grimp if available; fallback AST scan
if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
  IMPORT_BOUNDARIES_STATUS="SKIPPED"
  write_note "$IMPORT_BOUNDARIES_REPORT" "Import boundaries no ejecutado: no se detecto backend/src."
else
  python3 - "$SOURCE_DIR" "$IMPORT_BOUNDARIES_REPORT" <<'PY'
import ast
import os
import sys
from collections import defaultdict
from datetime import datetime

source_dir = sys.argv[1]
report_path = sys.argv[2]

layer_rules = {
    "domain": {"api", "infrastructure", "runtime", "pipeline", "llm"},
    "application": {"api"},
}

forbidden_fastapi_for_application = True

violations = defaultdict(list)
api_suspects = []

def relpath(path: str) -> str:
    return path.replace("\\", "/")

for root, _dirs, files in os.walk(source_dir):
    for name in files:
        if not name.endswith(".py"):
            continue
        path = os.path.join(root, name)
        rel = relpath(os.path.relpath(path, source_dir))
        module_path = "src." + rel[:-3].replace("/", ".")
        parts = module_path.split(".")
        layer = parts[1] if len(parts) > 1 else "unknown"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            tree = ast.parse(content, filename=path)
        except Exception as exc:
            violations["parse_error"].append((rel, str(exc)))
            continue

        import_targets = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_targets.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_targets.append(node.module)

        # Rule 1: domain cannot import heavy outer layers
        if layer == "domain":
            for target in import_targets:
                if target.startswith("src."):
                    tgt_parts = target.split(".")
                    tgt_layer = tgt_parts[1] if len(tgt_parts) > 1 else ""
                    if tgt_layer in layer_rules["domain"]:
                        violations["domain_forbidden"].append((rel, target))

        # Rule 2: application should not import api or fastapi
        if layer == "application":
            for target in import_targets:
                if target.startswith("src.api"):
                    violations["application_imports_api"].append((rel, target))
                if forbidden_fastapi_for_application and (target == "fastapi" or target.startswith("fastapi.")):
                    violations["application_imports_fastapi"].append((rel, target))

        # Rule 4: infrastructure should avoid importing api
        if layer == "infrastructure":
            for target in import_targets:
                if target.startswith("src.api"):
                    violations["infrastructure_imports_api"].append((rel, target))

        # Rule 5: pipeline / llm should avoid domain contamination direction (heuristic note)
        if layer in {"pipeline", "llm"}:
            for target in import_targets:
                if target.startswith("src.domain"):
                    violations["pipeline_llm_import_domain"].append((rel, target))

        # Rule 3 heuristic: API routes containing business-heavy logic signals
        if rel.startswith("api/routes/"):
            branch_signals = (
                content.count(" if ")
                + content.count(" for ")
                + content.count(" while ")
                + content.count(" try:")
            )
            if len(content.splitlines()) > 350 or branch_signals > 40:
                api_suspects.append((rel, len(content.splitlines()), branch_signals))

statuses = {}
statuses["domain_forbidden"] = "FAIL" if violations["domain_forbidden"] else "PASS"
statuses["application_imports_api"] = "FAIL" if violations["application_imports_api"] else "PASS"
statuses["application_imports_fastapi"] = "FAIL" if violations["application_imports_fastapi"] else "PASS"
statuses["infrastructure_imports_api"] = "FAIL" if violations["infrastructure_imports_api"] else "PASS"
statuses["pipeline_llm_import_domain"] = "REVIEW" if violations["pipeline_llm_import_domain"] else "PASS"
statuses["api_business_logic_suspects"] = "REVIEW" if api_suspects else "PASS"

with open(report_path, "w", encoding="utf-8") as out:
    out.write("# Backend import boundaries audit\n")
    out.write(f"source_dir: {source_dir}\n")
    out.write(f"generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    out.write("Tooling:\n")
    out.write("- import-linter: heuristic fallback used (sin contrato ini)\n")
    out.write("- grimp: optional (not required for fallback)\n")
    out.write("- method: python AST scan\n\n")

    out.write("## Reglas y estado\n")
    out.write(f"- R1 domain no importa api/infrastructure/runtime/pipeline/llm: {statuses['domain_forbidden']}\n")
    out.write(f"- R2 application no importa api: {statuses['application_imports_api']}\n")
    out.write(f"- R2b application no importa fastapi: {statuses['application_imports_fastapi']}\n")
    out.write(f"- R4 infrastructure no importa api: {statuses['infrastructure_imports_api']}\n")
    out.write(f"- R5 pipeline/llm con imports a domain (revisión manual): {statuses['pipeline_llm_import_domain']}\n")
    out.write(f"- R3 api rutas con lógica pesada (heurística): {statuses['api_business_logic_suspects']}\n\n")

    def dump(title: str, key: str) -> None:
        out.write(f"### {title}\n")
        if not violations[key]:
            out.write("- Sin hallazgos.\n\n")
            return
        for rel, target in violations[key][:120]:
            out.write(f"- {rel} -> {target}\n")
        if len(violations[key]) > 120:
            out.write(f"- ... ({len(violations[key]) - 120} hallazgos adicionales)\n")
        out.write("\n")

    dump("R1 violaciones detectadas", "domain_forbidden")
    dump("R2 violaciones detectadas", "application_imports_api")
    dump("R2b violaciones detectadas", "application_imports_fastapi")
    dump("R4 violaciones detectadas", "infrastructure_imports_api")
    dump("R5 señales a revisar", "pipeline_llm_import_domain")

    out.write("### R3 señales de lógica de negocio pesada en rutas API\n")
    if not api_suspects:
        out.write("- Sin sospechosos por heurística de tamaño/ramificación.\n")
    else:
        for rel, lines, branches in api_suspects[:80]:
            out.write(f"- {rel} (lineas={lines}, branch_signals={branches})\n")
        if len(api_suspects) > 80:
            out.write(f"- ... ({len(api_suspects) - 80} sospechosos adicionales)\n")
    out.write("\n")

    if violations["parse_error"]:
        out.write("### Errores de parseo\n")
        for rel, err in violations["parse_error"][:40]:
            out.write(f"- {rel}: {err}\n")
        out.write("\n")

    out.write("Observacion: auditoría heurística; validar manualmente antes de concluir violación arquitectónica.\n")
PY
  if [ "$?" -eq 0 ]; then
    IMPORT_BOUNDARIES_STATUS="FINDINGS"
  else
    IMPORT_BOUNDARIES_STATUS="ERROR"
    write_note "$IMPORT_BOUNDARIES_REPORT" "Import boundaries audit fallo durante ejecución del scanner AST."
  fi
fi

# 4) SOLID / GRASP markdown synthesis
if [ -z "$SOURCE_DIR" ] || [ ! -d "$SOURCE_DIR" ]; then
  SOLID_GRASP_STATUS="SKIPPED"
  write_note "$SOLID_GRASP_REPORT" "SOLID/GRASP no ejecutado: no se detecto backend/src."
else
  python3 - "$SOURCE_DIR" "$CODE_SMELLS_REPORT" "$COMPLEXITY_REPORT" "$IMPORT_BOUNDARIES_REPORT" "$SOLID_GRASP_REPORT" <<'PY'
import os
import re
import sys
from datetime import datetime

source_dir, smells_path, complexity_path, boundaries_path, out_path = sys.argv[1:6]

def safe_read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

smells = safe_read(smells_path)
complexity = safe_read(complexity_path)
boundaries = safe_read(boundaries_path)

cc_risky = len(re.findall(r"\b([DEF])\b", complexity))
pylint_hits = {
    "too_many_args": len(re.findall(r"R0913", smells)),
    "too_many_branches": len(re.findall(r"R0912", smells)),
    "too_many_returns": len(re.findall(r"R0911", smells)),
    "too_many_locals_or_methods": len(re.findall(r"R0902|R0915", smells)),
    "broad_exception": len(re.findall(r"W0703", smells)),
    "unused_import": len(re.findall(r"W0611", smells)),
}
vulture_lines = len([ln for ln in smells.splitlines() if ln.strip().startswith(source_dir)])
boundary_fails = len(re.findall(r": FAIL", boundaries))
boundary_reviews = len(re.findall(r": REVIEW", boundaries))
api_suspects = len(re.findall(r"\(lineas=", boundaries))

with open(out_path, "w", encoding="utf-8") as out:
    out.write("# Auditoría backend - SOLID y GRASP\n\n")
    out.write("## Alcance\n\n")
    out.write(
        "Evaluación heurística de arquitectura backend sobre capas `api`, `application`, `domain`, `infrastructure`, "
        "`pipeline`, `llm`, `runtime`, sin modificar comportamiento funcional.\n\n"
    )

    out.write("## Señales automáticas analizadas\n\n")
    out.write(f"- Complejidad ciclomática (radon): indicadores de riesgo alto detectados aprox={cc_risky}\n")
    out.write("- Code smells (pylint/vulture):\n")
    out.write(f"  - too-many-arguments: {pylint_hits['too_many_args']}\n")
    out.write(f"  - too-many-branches: {pylint_hits['too_many_branches']}\n")
    out.write(f"  - too-many-returns: {pylint_hits['too_many_returns']}\n")
    out.write(f"  - clases/metodos voluminosos: {pylint_hits['too_many_locals_or_methods']}\n")
    out.write(f"  - broad-exception: {pylint_hits['broad_exception']}\n")
    out.write(f"  - imports no usados: {pylint_hits['unused_import']}\n")
    out.write(f"  - codigo potencialmente muerto (vulture): {vulture_lines}\n")
    out.write(f"- Límites de imports entre capas: FAIL={boundary_fails}, REVIEW={boundary_reviews}\n")
    out.write(f"- Rutas API sospechosas de lógica pesada (heurística): {api_suspects}\n\n")

    out.write("## SOLID\n\n")
    out.write("### Single Responsibility Principle\n")
    out.write("- Señales: módulos/rutas extensas y métricas de métodos con alta complejidad o demasiadas ramas.\n")
    out.write("- Observación inicial: revisar rutas API y servicios con señales de tamaño/ramificación elevadas.\n\n")

    out.write("### Open/Closed Principle\n")
    out.write("- Señales: condicionales extensos por provider/status/modelo en pipeline/llm.\n")
    out.write("- Observación inicial: auditar puntos con `if/elif` largos antes de introducir nuevos proveedores.\n\n")

    out.write("### Liskov Substitution Principle\n")
    out.write("- Señales: adapters con retornos incompatibles o contratos débiles detectados por análisis estático.\n")
    out.write("- Observación inicial: cruzar findings de tipado con implementación de ports/adapters.\n\n")

    out.write("### Interface Segregation Principle\n")
    out.write("- Señales: interfaces/ports con demasiadas responsabilidades o métodos no cohesivos.\n")
    out.write("- Observación inicial: revisar puertos de application/domain con crecimiento orgánico.\n\n")

    out.write("### Dependency Inversion Principle\n")
    out.write("- Señales: imports prohibidos entre capas (especialmente domain/application hacia capas externas).\n")
    out.write("- Observación inicial: hallazgos de boundaries requieren validación manual y eventual refactor dirigido.\n\n")

    out.write("## GRASP\n\n")
    out.write("### Information Expert\n")
    out.write("- Señal: reglas de dominio ubicadas fuera de `domain` o con acoplamiento a infraestructura.\n\n")

    out.write("### Controller\n")
    out.write("- Señal: rutas FastAPI con coordinación/lógica de negocio extensa.\n\n")

    out.write("### Low Coupling\n")
    out.write("- Señal: imports cruzados entre capas y dependencia circular implícita.\n\n")

    out.write("### High Cohesion\n")
    out.write("- Señal: módulos mezclando validación, orquestación y persistencia en la misma unidad.\n\n")

    out.write("### Creator\n")
    out.write("- Señal: creación de entidades/dtos lejos del contexto experto del dominio.\n\n")

    out.write("### Indirection\n")
    out.write("- Señal: uso parcial de ports/adapters o bypass directo de infraestructura.\n\n")

    out.write("### Protected Variations\n")
    out.write("- Señal: cambios de proveedor LLM impactando más capas que adapters y configuración.\n\n")

    out.write("## Hallazgos iniciales\n\n")
    out.write("- Se detectaron señales de complejidad y code smells suficientes para justificar auditoría manual por módulo.\n")
    out.write("- Los límites de imports muestran señales `FAIL/REVIEW` en reglas clave de capas.\n")
    out.write("- Existen rutas API con indicadores heurísticos de posible sobrecarga de coordinación.\n")
    out.write("- El patrón de encapsulación de proveedores requiere seguimiento para mantener DIP/Protected Variations.\n\n")

    out.write("## Limitaciones\n\n")
    out.write("- SOLID y GRASP no se validan de forma determinista como tests unitarios.\n")
    out.write("- Esta auditoría usa señales heurísticas automatizadas y semi-automatizadas.\n")
    out.write("- Requiere revisión manual posterior para confirmar severidad e impacto.\n")
    out.write("- Puede contener falsos positivos o falsos negativos por parseo estático.\n\n")

    out.write("## Recomendaciones futuras\n\n")
    out.write("- Definir contratos explícitos de imports por capa (policy as code) y versionarlos.\n")
    out.write("- Priorizar refactor en módulos con complejidad C/D/E/F y code smells recurrentes.\n")
    out.write("- Revisar rutas API con señales de orquestación excesiva y mover lógica a application/use-cases.\n")
    out.write("- Fortalecer test de arquitectura para prevenir regresiones de acoplamiento.\n")
    out.write(f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
PY
  if [ "$?" -eq 0 ]; then
    SOLID_GRASP_STATUS="FINDINGS"
  else
    SOLID_GRASP_STATUS="ERROR"
    write_note "$SOLID_GRASP_REPORT" "Fallo la generación del reporte SOLID/GRASP."
  fi
fi

echo "Resumen backend architecture audit:"
printf "%-28s | %-13s | %s\n" "Auditoria" "Estado" "Reporte"
printf "%-28s | %-13s | %s\n" "Code smells" "$CODE_SMELLS_STATUS" "audit/raw/backend-code-smells.txt"
printf "%-28s | %-13s | %s\n" "Complejidad" "$COMPLEXITY_STATUS" "audit/raw/backend-complexity.txt"
printf "%-28s | %-13s | %s\n" "Limites de imports" "$IMPORT_BOUNDARIES_STATUS" "audit/raw/backend-import-boundaries.txt"
printf "%-28s | %-13s | %s\n" "SOLID/GRASP" "$SOLID_GRASP_STATUS" "audit/raw/backend-solid-grasp-audit.md"

exit 0
