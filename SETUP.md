# 🚀 Guía Rápida de Setup

## Pasos para configurar el proyecto

1. **Instalar dependencias:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Configurar variables de entorno:**
   ```bash
   cp env.example.txt .env
   ```
   
   Luego edita `.env` y agrega tu API key de Gemini:
   ```
   GEMINI_API_KEY=tu_api_key_aqui
   ```

3. **Verificar instalación:**
   ```bash
   python -c "import src; print('✅ Instalación correcta')"
   ```

## Estructura creada

✅ Carpetas del proyecto
✅ Archivos __init__.py
✅ pyproject.toml con dependencias
✅ .gitignore configurado
✅ README.md con documentación

## Próximos pasos

Ver el [Plan de Implementación](PLAN_IMPLEMENTACION.md) para continuar con la Fase 1.
