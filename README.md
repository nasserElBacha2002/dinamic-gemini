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
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```

3. **Instalar dependencias del backend:**
   ```bash
   pip install -e backend/
   pip install -e "backend/[dev]"   # con deps de desarrollo (pytest, black, ruff)
   ```

   La aplicación tiene **backend** (Python, en `backend/`) y **frontend** (React, en `frontend/`). Ver [REPO_STRUCTURE.md](REPO_STRUCTURE.md) para la estructura del repo.

   **Despliegue DEV** (rama `develop`, servidor Ubuntu/OpenCloud vía GitHub Actions + Docker): [docs/deployment/DEV-OPENCLOUD.md](docs/deployment/DEV-OPENCLOUD.md). `main` no es producción.

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

4. **SQL Server (Stage 8, opcional):** Si usas la API con persistencia en base de datos, configura en `.env` las variables `SQLSERVER_SERVER`, `SQLSERVER_DATABASE`, `SQLSERVER_UID`, `SQLSERVER_PWD`. En **macOS** hace falta instalar el driver ODBC para SQL Server; si no está instalado, la app usará solo el filesystem (sin errores). Para instalar el driver en macOS:
   ```bash
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   brew update
   brew install msodbcsql18 mssql-tools18
   ```
   (Acepta la licencia cuando lo pida.) Si prefieres el driver 17: `brew install msodbcsql17`. La app usará automáticamente el primer driver "SQL Server" que encuentre instalado.

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
├── backend/             # Backend Python (API, pipeline, jobs, persistencia)
│   ├── src/             # Código fuente (api, domain, application, pipeline, ...)
│   ├── tests/           # Tests del backend
│   ├── configs/         # Configuración del backend
│   ├── scripts/         # Scripts de utilidad
│   └── pyproject.toml   # Dependencias y entrada CLI (dinamic-gemini = src.app:main)
├── frontend/            # Frontend React/TypeScript (Vite)
│   ├── src/
│   ├── tests/
│   └── package.json
├── docs/                # Documentación del proyecto
├── output/              # Directorio de salida (generado por el backend)
├── .env.example         # Ejemplo de variables de entorno
├── REPO_STRUCTURE.md    # Dónde añadir código (backend vs frontend)
└── README.md            # Este archivo
```

## 🧪 Testing

Ejecutar tests:

```bash
pytest
```

Con cobertura (desde la raíz; usa `pytest.ini` que apunta a `backend/tests`):

```bash
pytest
# o: pytest --cov=src --cov-report=html
```

## 📝 Desarrollo

### Desarrollo local (full-stack)

Para levantar backend (Python) y frontend (React) con un solo comando desde la raíz del repo, usa **`./dev.sh`** (recomendado) o `npm run dev`. Detalles: [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md).

### Formateo de código

Desde la raíz (el backend está en `backend/`):

```bash
black backend/src backend/tests
ruff check backend/src backend/tests
```

### Type checking

```bash
mypy backend/src
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