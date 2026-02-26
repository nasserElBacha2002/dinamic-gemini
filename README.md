# 🎥 Dinamic Gemini - Sistema de Conteo de Inventario por Video

Sistema en Python que procesa videos de depósito, extrae fotogramas estratégicamente y utiliza la API de Gemini para contar cajas por pallet, generando un reporte JSON estructurado.

## 📋 Características

- ✅ Extracción configurable de frames de video
- ✅ Integración con Gemini API para análisis de visión
- ✅ Consolidación robusta de resultados multi-frame usando MAD (Median Absolute Deviation)
- ✅ Exportación de resultados en JSON estructurado
- ✅ Manejo robusto de errores y reintentos
- ✅ Optimización de costos (compresión, límite de frames)

## 🚀 Instalación

### Requisitos

- Python 3.9 o superior
- pip o poetry

### Pasos de instalación

1. **Clonar el repositorio:**
   ```bash
   git clone <repository-url>
   cd dinamic-gemini
   ```

2. **Crear entorno virtual (recomendado):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -e ".[dev]"
   ```

   O si prefieres instalar solo las dependencias de producción:
   ```bash
   pip install -e .
   ```

## ⚙️ Configuración

1. **Copiar el archivo de ejemplo de variables de entorno:**
   ```bash
   cp .env.example .env
   ```

2. **Editar `.env` y agregar tu API key de Gemini:**
   ```env
   GEMINI_API_KEY=tu_api_key_aqui
   ```

   Puedes obtener tu API key en: https://makersuite.google.com/app/apikey

3. **Configurar otros parámetros (opcional):**
   - `EXTRACT_FPS`: Frames por segundo a extraer (default: 1.0)
   - `MAX_FRAMES_TO_SEND`: Máximo de frames a procesar (vacío/0 = sin límite; opcional para debug, ej. 200). `FRAME_STRIDE`: cada cuántos frames tomar (default: 1).
   - `RESIZE_MAX_SIDE`: Tamaño máximo de lado para redimensionar (default: 1280)
   - `OUTPUT_DIR`: Directorio de salida (default: output)
   - `DEBUG_SAVE_FRAMES`: Guardar frames procesados para debug (default: false)

## 📖 Uso

### Uso básico desde CLI

```bash
python -m src.cli --video data/mi_video.mp4 --video-id VID_001
```

### Opciones disponibles

```bash
python -m src.cli \
  --video data/VID_001.mp4 \
  --video-id VID_001 \
  --fps 1.0 \
  --max-frames 20 \
  --resize 1280 \
  --output output/ \
  --debug
```

**Parámetros:**
- `--video` (requerido): Ruta al archivo de video
- `--video-id`: Identificador del video (default: auto-generado)
- `--fps` / `--extract-fps`: Frames por segundo a extraer
- `--max-frames`: Máximo de frames a enviar a Gemini
- `--resize` / `--resize-max-side`: Tamaño máximo para redimensionar
- `--output` / `--output-dir`: Directorio de salida
- `--debug`: Activar modo debug (guarda frames procesados)

### Salida

El sistema genera un archivo `result.json` en el directorio de salida con la siguiente estructura:

```json
{
  "video_id": "VID_001",
  "pallets": [
    {
      "pallet_id": "PALLET_001",
      "products": [
        {
          "brand": "Cremigal",
          "product": "Leche UAT Entera 12x1L",
          "estimated_boxes": 84,
          "confidence": 0.93
        }
      ]
    }
  ]
}
```

## 🏗️ Estructura del Proyecto

```
dinamic-gemini/
├── src/
│   ├── models/          # Modelos Pydantic (schemas)
│   ├── video/           # Módulo de procesamiento de video
│   ├── preprocess/      # Preprocesamiento de imágenes
│   ├── llm/             # Integración con Gemini API
│   ├── consolidate/     # Consolidación de resultados
│   ├── io/              # I/O y exportación
│   └── cli.py           # Interfaz de línea de comandos
├── tests/               # Tests unitarios e integración
├── output/              # Directorio de salida (generado)
├── configs/             # Archivos de configuración
├── data/                # Videos de prueba (opcional)
├── pyproject.toml       # Configuración del proyecto
├── .env.example         # Ejemplo de variables de entorno
└── README.md            # Este archivo
```

## 🧪 Testing

Ejecutar tests:

```bash
pytest
```

Con cobertura:

```bash
pytest --cov=src --cov-report=html
```

## 📝 Desarrollo

### Formateo de código

```bash
black src/ tests/
ruff check src/ tests/
```

### Type checking

```bash
mypy src/
```

## 🔒 Seguridad

- **Nunca** commitees el archivo `.env` con tu API key
- La API key solo se carga desde variables de entorno
- Los logs no incluyen información sensible

## 📚 Documentación

- [Plan de Implementación](PLAN_IMPLEMENTACION.md) - Plan detallado de desarrollo
- [Documento Técnico](Sprint%205%20-%20Gemini.md) - Especificación técnica completa

## 🐛 Troubleshooting

### Error: "Falta GEMINI_API_KEY"
- Verifica que el archivo `.env` existe y contiene `GEMINI_API_KEY`
- Asegúrate de que `python-dotenv` está instalado

### Error: "No se pudo abrir el video"
- Verifica que el archivo existe y el path es correcto
- Verifica que el formato de video es soportado (mp4, mov, etc.)
- Asegúrate de que OpenCV puede leer el archivo

### Error: Rate limit de Gemini API
- Usa `--max-frames 200` o `MAX_FRAMES_TO_SEND=200` para limitar frames
- Espera unos minutos antes de reintentar
- Considera usar un modelo diferente o aumentar el tiempo entre requests

## 📄 Licencia

MIT License

## 👥 Contribuidores

Dinamic Systems

## 🔗 Enlaces Útiles

- [Documentación de Gemini API](https://ai.google.dev/docs)
- [OpenCV Documentation](https://docs.opencv.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**Estado del proyecto:** 🚧 En desarrollo (MVP)