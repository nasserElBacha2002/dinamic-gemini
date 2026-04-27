#!/usr/bin/env sh
set -u

echo "== Quality Gate (placeholder) - Security audit =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"

mkdir -p "$RAW_DIR"

echo "Directorio de evidencia preparado: $RAW_DIR"
echo "En fases futuras se ejecutaran:"
echo "- Trivy"
echo "- OWASP ZAP baseline scan"
echo
echo "Estado actual: placeholder seguro (sin ejecutar herramientas reales)."
exit 0
