#!/usr/bin/env sh
set -u

echo "== Quality Gate (placeholder) - Backend audit =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"

mkdir -p "$RAW_DIR"

echo "Directorio de evidencia preparado: $RAW_DIR"
echo "En fases futuras se ejecutaran:"
echo "- Ruff"
echo "- Mypy"
echo "- Bandit"
echo "- pip-audit"
echo "- Pytest"
echo
echo "Chequeo de herramientas disponibles en el entorno actual:"
for tool in ruff mypy bandit pip-audit pytest; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "- $tool: OK"
  else
    echo "- $tool: NO INSTALADO"
  fi
done
echo
echo "Estado actual: placeholder seguro (sin ejecutar herramientas reales)."
exit 0
