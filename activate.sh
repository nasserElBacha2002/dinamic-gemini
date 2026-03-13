#!/bin/bash
# Script de activación rápida del entorno virtual (desde la raíz del repo)

if [ ! -d ".venv" ]; then
    echo "❌ Error: .venv no encontrado. Creando..."
    python3 -m venv .venv
fi

echo "🔧 Activando entorno virtual..."
source .venv/bin/activate

echo "✅ Entorno virtual activado!"
echo ""
echo "📦 Para instalar el backend, ejecuta:"
echo "   pip install -e backend/"
echo "   pip install -e \"backend/[dev]\"   # con deps de desarrollo"
echo ""
echo "💡 Para desactivar el entorno, ejecuta:"
echo "   deactivate"
