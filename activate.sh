#!/bin/bash
# Script de activación rápida del entorno virtual

if [ ! -d "venv" ]; then
    echo "❌ Error: venv no encontrado. Creando..."
    python3 -m venv venv
fi

echo "🔧 Activando entorno virtual..."
source venv/bin/activate

echo "✅ Entorno virtual activado!"
echo ""
echo "📦 Para instalar dependencias, ejecuta:"
echo "   pip install -e \".[dev]\""
echo ""
echo "💡 Para desactivar el entorno, ejecuta:"
echo "   deactivate"
