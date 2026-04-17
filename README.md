# Dinamic Inventory — Plataforma v3 (API + frontend + pipeline)


Monorepo para la **plataforma operativa de inventarios v3**: API REST (FastAPI), aplicación web (React + Vite), persistencia en **Microsoft SQL Server**, almacenamiento de **artefactos** (local o S3), jobs de procesamiento (CV + LLM según configuración) y autenticación administrativa para el operador.

El repositorio incluye además un **CLI de pipeline por vídeo** (`python -m src.app`) orientado a ejecución batch; el flujo principal de producto es la **API v3** + **worker de jobs** + **frontend**.

---

## Estructura del repositorio

| Ruta | Contenido |
|------|-----------|
| `backend/` | Paquete Python `src`: API (`src.api`), dominio, casos de uso, infraestructura, jobs, pipeline CV/LLM, migraciones SQL, configuración (`src.config` + `src.env_settings`). |
| `frontend/` | SPA React + TypeScript (Vite): inventarios, pasillos, posiciones, resultados, cola de revisión, métricas, administración de IA (según rol). |
| `docs/` | Documentación de etapas, despliegue y decisiones. |
| `output/` | Directorio por defecto de salida local (artefactos y datos cuando `ARTIFACT_STORAGE_PROVIDER=local`). |
| `scripts/` | `run-backend.js` usado por `npm run dev:backend` en la raíz. |
| `dev.sh` | Arranque recomendado: API + Vite con variables coherentes y worker bajo demanda. |
| `.env.example` | Plantilla de variables de entorno (raíz; ver también `frontend/.env.example`). |
| `REPO_STRUCTURE.md` | Convenciones de carpetas y dónde añadir código. |
| `pytest.ini` | Tests del backend desde la raíz (`pythonpath=backend`). |

---

## Stack tecnológico

- **Backend:** Python 3.9+ (recomendado 3.11+ para desarrollo), FastAPI, Uvicorn, Pydantic v2, PyODBC (SQL Server), Passlib/bcrypt, PyJWT.
- **Frontend:** React 18, TypeScript, Vite 5, MUI, TanStack Query, react-i18next.
- **Base de datos:** SQL Server (ODBC).
- **Almacenamiento de artefactos:** filesystem bajo `OUTPUT_DIR` o **Amazon S3** (presigned URLs cuando aplica).
- **Tests:** pytest (backend), Vitest (frontend).

---

## Arquitectura en ejecución

1. **API HTTP** (`src.api.server:app`): monta routers v3 (`/api/v3/...`), autenticación (`/auth/...`), analytics, cola de revisión y configuración IA admin. Middleware opcional `X-API-Key` si `API_KEY` está definida.
2. **Worker de jobs:** puede ejecutarse en el **mismo proceso** que la API (`EMBEDDED_WORKER_ENABLED=true`, hilo en startup) o como **proceso separado** (`python -m src.jobs.run_worker`). En `./dev.sh` el worker embebido se **desactiva** y se define `WORKER_ON_DEMAND_COMMAND` para lanzar workers bajo demanda.
3. **Frontend:** consume la API; en desarrollo, `VITE_API_BASE_URL` vacío usa el **proxy** de Vite (`/api`, `/auth`, `/health` → `http://localhost:8000`).
4. **Guardas de esquema:** al arranque, si SQL está habilitado y configurado, se puede validar compatibilidad de migraciones (`DB_SCHEMA_*`); `/ready` devuelve 503 si el esquema es incompatible.

Referencias de código: `backend/src/api/server.py`, `backend/src/config.py`, `backend/src/env_settings/grouped_settings.py`.

---

## Requisitos previos

- **Python** 3.9 o superior y `pip`.
- **Node.js** 18+ y `npm` (para el frontend y scripts `npm run dev` en la raíz).
- **SQL Server** accesible por ODBC si usás persistencia (`SQLSERVER_ENABLED=true`); en macOS/Linux instalá un driver ODBC para SQL Server (p. ej. Microsoft ODBC 18).
- **Opcional:** credenciales de proveedores LLM según el modo de procesamiento (Gemini, OpenAI, Anthropic, DeepSeek).

---

## Instalación

### Backend

Desde la **raíz del repo**:

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

(O instalá en otro venv y asegurate de usar ese intérprete para `uvicorn` y `pytest`.)

### Frontend

```bash
cd frontend && npm install
```

### Variables de entorno

```bash
cp .env.example .env
# Opcional: frontend/.env.local con VITE_API_BASE_URL si no usás el proxy de Vite
```

La API carga, en orden: `.env` en la **raíz del repo**, luego `backend/.env` (sobrescribe claves del primero para overrides locales). Ver `backend/src/config.py` (`_load_dotenv_files`).

---

## Configuración

- **Lista canónica de variables:** definidas en `backend/src/env_settings/grouped_settings.py` (y lecturas puntuales en `env_settings/parsing.py`, `sqlserver_resolution.py`, `api/server.py`, `jobs/run_worker.py`, `infrastructure/services/on_demand_worker_launch_service.py`).
- **Plantilla:** `.env.example` en la raíz (bloques comentados). **No** subas `.env` con secretos.

Variables **imprescindibles** según escenario:

| Escenario | Variables típicas |
|-----------|-------------------|
| API + SQL | Cadena ODBC o `SQLSERVER_SERVER` + `SQLSERVER_DATABASE` + `SQLSERVER_UID` + `SQLSERVER_PWD` |
| Login v3 en UI | `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `AUTH_TOKEN_SECRET`; opcional `AUTH_JAIRO_PASSWORD_HASH` (**Jairo**) solo si el admin primario ya está configurado (ver nota abajo) |
| Pipeline con LLM | Según proveedor: p. ej. `GEMINI_API_KEY` si `LLM_PROVIDER=gemini` |
| Artefactos en S3 | `ARTIFACT_STORAGE_PROVIDER=s3`, `ARTIFACT_S3_BUCKET`, etc. |

**Usuario temporal por env (Jairo)** — no sustituye multi-usuario ni administración de cuentas: sin registro, sin UI de usuarios, sin modelo de permisos por recurso. El login fijo es exactamente **`Jairo`** (case-sensitive); la clave va solo como **hash** en `AUTH_JAIRO_PASSWORD_HASH` (vacío = desactivado). **Requiere** `ADMIN_USERNAME` y `ADMIN_PASSWORD_HASH` definidos: Jairo es un agregado opcional al admin primario. Ambos comparten el rol JWT `administrator` para la mayoría de v3; la inspección de configuración IA (`GET /api/v3/admin/ai-config`) queda limitada al principal primario (`AuthUser.id` `admin`). Los tokens antiguos sin claim `principal_id` se interpretan como ese principal primario.

---

## Cómo ejecutar el backend

Desde el directorio **`backend/`** (el `cwd` importa para imports `src.*`; `PYTHONPATH` debe ser el directorio `backend/`):

```bash
cd backend
source .venv/bin/activate   # si usás venv en backend/
uvicorn src.api.server:app --reload --port 8000
```

Equivalente desde la raíz (como hace `npm run dev:backend` / `scripts/run-backend.js`): `PYTHONPATH=backend` y `cwd=backend`.

**Arranque conjunto API + frontend (recomendado):**

```bash
./dev.sh
```

o, desde la raíz con dependencia `concurrently`:

```bash
npm install   # una vez, en la raíz
npm run dev
```

`./dev.sh` exporta `.env` de la raíz, fuerza `EMBEDDED_WORKER_ENABLED=false` y define `WORKER_ON_DEMAND_COMMAND` por defecto para workers hijos.

---

## Cómo ejecutar el frontend

```bash
cd frontend && npm run dev
```

Por defecto Vite escucha en **http://127.0.0.1:5173** y proxifica `/api`, `/auth` y `/health` al backend en `http://localhost:8000` (`frontend/vite.config.js`).

Variable **`VITE_API_BASE_URL`**: vacía = mismo origen + proxy. Si la definís (p. ej. URL absoluta del API), las peticiones van directo a ese host.

---

## Migraciones y esquema

CLI (desde **`backend/`** con el paquete instalado, o con `PYTHONPATH` apuntando a `backend/`):

```bash
cd backend
python scripts/db_migrate.py config-check   # preflight JSON, exit 3 si no hay cadena ODBC
python scripts/db_migrate.py status
python scripts/db_migrate.py validate
python scripts/db_migrate.py apply
```

Equivalente: `python -m src.database.migrations ...` (misma CLI en `src/database/migrations/cli.py`).

Variables relacionadas: `DB_SCHEMA_GUARD_ENABLED`, `DB_SCHEMA_GUARD_BLOCK_STARTUP`, `DB_SCHEMA_REQUIRED_VERSION`, `DB_SCHEMA_SERVICE_NAME`, `DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC`, `DEPLOYMENT_ID`.

---

## Health y readiness

| Ruta | Comportamiento |
|------|----------------|
| `GET /health` | JSON (`HealthResponse`): `ok`, metadatos de guard de esquema, versiones requerida/actual, `deploy_git_sha` opcional desde `GIT_SHA`. **No** exige `X-API-Key` aunque `API_KEY` esté definida. |
| `GET /ready` | 200 si el esquema es compatible (o el guard no falló); **503** con cuerpo JSON si `SCHEMA_INCOMPATIBLE`. |

---

## Artefactos y almacenamiento

- **`ARTIFACT_STORAGE_PROVIDER`:** `local` (default) escribe bajo `OUTPUT_DIR`; `s3` usa bucket/región/prefijo y URLs firmadas (`ARTIFACT_S3_*`, `ARTIFACT_S3_SIGNED_URL_TTL_SEC`).
- **`ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED`:** compatibilidad para leer rutas históricas en disco cuando el proveedor activo es S3.

---

## CLI de pipeline por vídeo (legacy / batch)

Entrada separada del flujo web v3; útil para procesar un archivo local con el pipeline híbrido:

```bash
cd backend
python -m src.app /ruta/al/video.mp4 --video-id VID_001
```

Opciones y modos: `python -m src.app --help`. Requiere las mismas variables de entorno de pipeline/LLM que el worker.

---

## Testing

**Backend** (desde la raíz; respeta `pytest.ini`):

```bash
pytest
```

**Frontend:**

```bash
cd frontend && npm run typecheck && npm test
```

---

## Docker (opcional)

En `backend/` existen `Dockerfile`, `Dockerfile.worker` y `docker-compose.yml` para entornos containerizados; revisá esos archivos para variables y puertos concretos del compose.

---

## Troubleshooting

- **401 / sin sesión en el frontend:** configurá auth (`ADMIN_*`, `AUTH_TOKEN_SECRET`; `AUTH_JAIRO_PASSWORD_HASH` solo con admin primario ya configurado) y reiniciá API + navegador.
- **503 en `/ready`:** revisá migraciones y `DB_SCHEMA_REQUIRED_VERSION` vs versión aplicada en la base.
- **403 `X-API-Key`:** la API tiene `API_KEY` definida; enviá el header o vaciá la variable solo en desarrollo local.
- **ODBC / SQL Server:** ejecutá `python scripts/db_migrate.py config-check` y revisá el JSON de error (sin secretos).
- **Proxy CORS:** si el frontend corre en otro origen, ajustá `CORS_ALLOW_ORIGINS` (lista separada por comas). Si está vacío, el servidor usa por defecto `http://localhost:5173` y `http://127.0.0.1:5173`.

---

## Documentación adicional

- `REPO_STRUCTURE.md` — estructura y convenciones.
- `backend/README.md` — detalle del backend, worker dev y checklist local.
- `docs/` — guías de despliegue y etapas (rutas concretas según lo que exista en el repo).
- **Inconsistencia conocida:** el README histórico citaba `docs/LOCAL_DEV.md`; el arranque local documentado aquí y en `dev.sh` / `REPO_STRUCTURE.md` sustituye esa referencia.

---

## Licencia y créditos

MIT License — Dinamic Systems.
