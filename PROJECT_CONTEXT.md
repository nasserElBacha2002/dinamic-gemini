# PROJECT_CONTEXT — Dinamic Inventory (dinamic-gemini)

> Generado por auditoría read-only del repositorio.  
> **Fuente de verdad:** código vigente + migraciones SQL. Cuando la documentación diverge, se documenta la discrepancia.  
> **Fecha de inspección:** 2026-08-27  
> **Git:** branch `develop` (= `main` = `origin/develop` @ `ed7b9233`), working tree limpio.

---

## 1. Resumen ejecutivo

**Dinamic Inventory** es una plataforma operativa de inventarios de almacén (v3) que combina:

1. **Plataforma operativa** — API REST FastAPI, SPA React, app móvil Expo/Android de captura, SQL Server, jobs de procesamiento.
2. **Subsistema de procesamiento** — pipeline CV/LLM (híbrido) sobre fotos/vídeo de pasillos (aisles) para identificar productos/posiciones, con modos `CODE_SCAN`, `INTERNAL_OCR` y `LEGACY_LLM`.

**Problema de negocio:** contar e identificar productos en pasillos a partir de imágenes (dron/cámara), con revisión humana, evidencia trazable, exportes y analytics de costo/calidad — sin adivinar cuando la evidencia es insuficiente (`UNKNOWN` / errores deterministas).

**Estado general:** producto maduro en desarrollo activo (releases 2.x→3.x, migraciones hasta `0097`, mobile en hardening Fase 3+). No hay multi-usuario/RBAC completo: auth administrativa por env (admin + opcional Jairo). Deploy DEV: backend OpenCloud (Docker Compose) + frontend Vercel Git. `main`/`develop` están alineados; **no hay evidencia de rama de producción dedicada** (workflows lo dejan explícito).

---

## 2. Stack tecnológico

| Área | Tecnología | Notas |
|------|------------|--------|
| Backend | Python ≥3.10 (recomendado 3.11+), FastAPI, Uvicorn, Pydantic v2 | Paquete `dinamic-gemini` en `backend/pyproject.toml` |
| Persistencia | Microsoft SQL Server vía PyODBC | Schema guard + migraciones versionadas |
| Auth | Passlib/bcrypt, PyJWT (HS256) | Refresh tokens **in-memory** (proceso) |
| Frontend | React 18, TypeScript ~5.4, Vite 6, MUI 5, TanStack Query 5, react-router 7, i18next | Runtime i18n **solo español** |
| Mobile | Expo ~51, RN 0.74, expo-sqlite, SecureStore | Android `com.dinamic.inventory.capture`; photos-only |
| LLM | Google Gemini (`google-genai`), OpenAI, Anthropic (Claude); DeepSeek legacy | Registry en `pipeline/providers` |
| Storage | Local FS, AWS S3, Google GCS | DEV OpenCloud tipicamente GCS |
| OCR / codes | Tesseract, ZBar (`libzbar0`) | En imagen Docker API/worker |
| CV (legacy/CLI) | OpenCV, NumPy, Pillow (+ HEIF) | CLI `python -m src.app` |
| Tests | pytest (+cov), Vitest, Jest (mobile) | Ruff, Black, mypy, bandit, pip-audit |
| Package managers | pip/setuptools (`backend/`), npm (root, frontend, mobile) | |
| CI | GitHub Actions | Quality gates + deploy OpenCloud + mobile validate/release |
| Observabilidad | Prometheus metrics + alertas Phase 5 | `deploy/prometheus/` |

---

## 3. Arquitectura

```
┌─────────────┐   JWT    ┌──────────────────┐  ODBC   ┌────────────┐
│ Frontend    │─────────▶│ FastAPI (api)    │────────▶│ SQL Server │
│ (Vercel)    │          │ /api/v3, /auth   │         └────────────┘
└─────────────┘          │                  │
┌─────────────┐          │  On-demand       │  S3/GCS ┌────────────┐
│ Mobile      │─────────▶│  worker spawn    │────────▶│ Artifacts  │
│ (Android)   │          │  python -m       │         └────────────┘
└─────────────┘          │  src.jobs.run_worker
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐     ┌─────────────┐
                         │ V3JobExecutor /  │────▶│ Gemini /    │
                         │ Hybrid pipeline  │     │ OpenAI /    │
                         └──────────────────┘     │ Anthropic   │
                                                  └─────────────┘
```

**Capas backend (clean architecture, enforced por tests):**

- `api` → `application` (use cases + ports) → `domain`
- `infrastructure` implementa ports (repos SQL, storage, queue, pipeline executor)
- `runtime/` DI (`app_container`, builders)
- Cross-cutting: `auth/`, `jobs/`, `pipeline/`, `llm/`, `observability/`, módulos CV clásicos

**Workers:**

| Modo | Mecanismo |
|------|-----------|
| Embedded | Hilo en API si `EMBEDDED_WORKER_ENABLED=true` (default) |
| On-demand | `WORKER_ON_DEMAND_COMMAND` spawnea proceso por job (`./dev.sh` y OpenCloud) |
| Dedicated | `python -m src.jobs.run_worker` / `Dockerfile.worker` |
| Outbox | Artifact publication worker (flag) |

**Cola:** no Redis/SQS. Producción = claim SQL sobre `inventory_jobs`. Fallback in-memory si SQL deshabilitado.

---

## 4. Estructura del repositorio

| Ruta | Responsabilidad |
|------|-----------------|
| `backend/src/api/` | FastAPI app, routes v3, schemas, middleware, schema guard |
| `backend/src/application/` | Use cases, ports, DTOs, services de aplicación |
| `backend/src/domain/` | Entidades y políticas de dominio |
| `backend/src/infrastructure/` | Repos SQL, storage S3/GCS, queue, OCR, code scanning, executors |
| `backend/src/pipeline/` | Pipeline híbrido por stages |
| `backend/src/llm/` | Clientes/adapters LLM + prompt composition |
| `backend/src/jobs/` | Worker loop, claim, legacy bridge |
| `backend/src/database/` | `schema.sql`, migraciones `versions/0001–0097`, ODBC client |
| `backend/src/auth/` | Login/JWT/refresh |
| `backend/src/detection|tracking|consolidate|reporting|…` | CV clásico / CLI track pipeline |
| `backend/tests/` | ~591 `test_*.py` |
| `frontend/src/` | SPA: pages, features, api client, hooks, i18n |
| `frontend/tests/` | ~220 tests Vitest |
| `mobile/` | Cliente captura Android + SQLite local + upload queue |
| `docs/` | Deployment, ADRs, capture sessions, quality gate |
| `audit/`, `review/` | Artefactos de auditorías/fases (no runtime) |
| `contracts/` | JSON schemas (code-scan, product-labels) |
| `deploy/prometheus/` | Alertas Phase 5 |
| `deployment/archive/` | Legacy AWS ECS + Vercel CLI GHA |
| `scripts/` | `run-backend.js`, quality gate, ops |
| `secrets/` | Montaje de credenciales (no committear keys) |
| `output/`, `data/output/` | Artefactos locales / volumen Docker |
| `.github/workflows/` | CI/CD |
| `dev.sh`, `.env.example` | Arranque local y plantilla de config |

**Relación:** el frontend y mobile son clientes del mismo contrato `/auth` + `/api/v3`. El worker ejecuta el mismo código de pipeline que puede dispararse vía CLI legacy (`src.app`).

---

## 5. Modelo de dominio

**Entidades centrales:**

| Concepto | Rol |
|----------|-----|
| **Client / ClientSupplier** | Tenancy comercial; prompts y extraction profiles por proveedor |
| **Inventory** | Contenedor de un conteo (modo production/test; soft-delete) |
| **Aisle** | Pasillo con assets, jobs, estados de ciclo de vida, `is_active` |
| **Job (`inventory_jobs`)** | Ejecución de procesamiento (lease, claim, finalization) |
| **SourceAsset** | Foto/vídeo subido |
| **Position / ProductRecord / Evidence** | Resultado por posición + productos + evidencia |
| **ReviewAction** | Correcciones humanas |
| **Capture / OrderedCapture** | Sesiones de captura (web/mobile) y secuencia |
| **CodeScan / Authoritative local scan** | Detección de códigos (servidor o mobile) |
| **Position labels / reconciliation / overrides** | Posicionamiento físico con QR firmados |
| **AisleRevision / ServerReprocess** | Versionado y reprocesos |
| **Local CSV / Inventory packages** | Importes offline/mobile |

**Invariantes de procesamiento (producto):** un producto por pallet cuando aplica; evidencia insuficiente → `UNKNOWN` / `INSUFFICIENT_EVIDENCE` (no inventar).

---

## 6. Modelo de datos

**Bootstrap:** `backend/src/database/schema.sql` (snapshot histórico idempotente; ~38 `CREATE TABLE`)  
**Incremental:** `backend/src/database/migrations/versions/` → **última: `0097_positions_merge.sql`**  
**Contrato de instalación (código):** `0001_baseline.sql` es solo un marcador (`SELECT 1`). Entornos nuevos deben: (1) aplicar `schema.sql`, (2) correr migraciones `0001`…`0097`. Un DB ya migrado hasta `0097` está completo aunque `schema.sql` no liste todas las tablas.

**Relación schema.sql ↔ migraciones (verificado 2026-08-27):**

| Hecho | Detalle |
|-------|---------|
| Columnas recientes en bootstrap | `inventories.deleted_at` (0096) y `positions.merged_into_position_id` (0097) **sí** están en `schema.sql` |
| Tablas solo en migraciones | ~42 `CREATE TABLE` (p. ej. code scans, artifact outbox, authoritative finalization, server reprocess, aisle revisions, `client_position_labels`, local CSV/packages, preliminary detections) **no** tienen `CREATE TABLE` en `schema.sql` |
| Convención de mantenimiento | Varias migraciones dicen “Keep aligned with schema.sql”; en la práctica el bootstrap se actualizó de forma parcial (ALTER en tablas core + algunos bloques positioning/processing), no como dump 1:1 de 0097 |
| Riesgo real | Usar **solo** `schema.sql` sin `db_migrate apply` deja el schema incompleto. Con bootstrap + apply hasta 0097, no hay “hueco” operativo. Drift de docs/mantenimiento, no de DBs ya migradas |

### Tablas / áreas clave

| Área | Tablas (representativas) |
|------|--------------------------|
| Tenancy | `clients`, `client_suppliers` |
| Core | `inventories`, `aisles`, `inventory_jobs`, `source_assets` |
| Resultados | `positions`, `product_records`, `evidences`, `review_actions`, `result_evidence` |
| Capture | `capture_sessions` (+ items/groups), `ordered_capture_sessions` |
| Processing | `job_asset_processing_states`, attempts, leases, `processing_events`, external requests |
| Code / mobile | aisle code scans, preliminary detections, authoritative scans/finalization |
| Positioning | `aisle_locations`, label tables, detections, reconciliation, overrides |
| Ops | artifact outbox/manifest, server reprocess, aisle revisions |
| Soft delete | `inventories.deleted_at`, `deleted_by` (0096) |
| Merge | `positions.merged_into_position_id` (0097) |

### Estados (CHECK / enums)

- **Inventory:** `draft`, `processing`, `in_review`, `completed`, `failed` (+ soft-delete fuera de status)
- **Aisle:** `created` → `assets_uploaded` → `queued` → `processing` → `processed` → `in_review` → `completed` \| `failed`; `is_active`
- **Job:** `queued`, `starting`, `running`, `cancel_requested`, `canceled`, `timed_out`, `succeeded`, `failed`
- **Identification mode:** `CODE_SCAN`, `INTERNAL_OCR`, `LEGACY_LLM`
- **Ordered capture:** `OPEN`, `UPLOADING`, `SEALED`, `PROCESSING`, `COMPLETED`, `FAILED`

Timestamps y auditoría: `created_at`/`updated_at` habituales; finalization/recovery metadata en jobs; review_actions con tipado de acción.

---

## 7. Flujos principales

### 7.1 Login operador (web/mobile)

1. `POST /auth/login` con username/password.
2. Valida hashes env (admin primario; opcional `Jairo`).
3. Emite JWT access + refresh (refresh store en memoria del proceso).
4. Cliente guarda token (localStorage / SecureStore) y llama `GET /auth/me`.
5. Errores: 401 credenciales, 503 sin `AUTH_TOKEN_SECRET`.

### 7.2 Inventario → pasillo → upload → process (happy path web)

1. UI: crear inventario (`POST /api/v3/inventories`) → crear aisle → upload assets (`POST .../aisles/{id}/assets`).
2. `POST .../aisles/{id}/process` → `StartAisleProcessing` → persiste job `QUEUED`/`STARTING` → lanza worker on-demand.
3. Worker claim (`inventory_jobs`) → `V3JobExecutor` → HybridInventoryPipeline (stages) y/o estrategias CODE_SCAN/OCR.
4. Persist resultados (`persist_aisle_result`, consolidation) → artefactos local/S3/GCS → aisle/inventory status.
5. UI: posiciones, review, export CSV, analytics.
6. Errores típicos: schema incompatible (503 `/ready`), `WORKER_LAUNCH_FAILED`, lease/timeout, provider LLM errors, 404 scoping.

### 7.3 Captura mobile

1. Login → listar inventarios/aisles.
2. Capture session local (SQLite) + opcional ordered-capture en backend.
3. Upload queue (micro-batches multipart) con leases; pause offline.
4. Opcional: local CODE_SCAN → preliminary / authoritative sync.
5. `process` aisle + review local / finalization / offline ops queue.
6. Servidor permanece autoridad de verdad.

### 7.4 Revisión de posiciones

1. List/detail positions → `POST .../reviews` (confirm, update qty/sku/code, mark unknown, merge).
2. Validación run-scoped vs legacy `job_id IS NULL`.
3. Soft-delete inventory / deactivate aisle afectan listados y acceso.

### 7.5 Admin AI / storage

1. Solo principal primario (`AuthUser.id == "admin"`).
2. `GET /api/v3/admin/ai-config`, storage cleanup, finalization recovery.
3. Frontend gatea por `username === 'admin'` (además del JWT).

---

## 8. Autenticación y permisos

| Aspecto | Implementación |
|---------|----------------|
| Usuarios | Solo env: `ADMIN_*` + opcional `AUTH_JAIRO_PASSWORD_HASH` — **no** DB users / registro |
| Tokens | JWT HS256; claims `sub`, `principal_id`, `username`, `role`, opcional `client_id` |
| Roles backend | `platform_admin` (sin client) / `company_admin` (con `AUTH_*_CLIENT_ID`) |
| Legacy role | JWT `administrator` aceptado como platform alias (schemas) |
| Frontend types | `AuthRole = 'administrator'` — **desalineado** con roles backend actuales |
| Refresh | Dict in-process; reinicio/multi-instancia invalida refresh |
| API key | Opcional Model A: `API_KEY` + `API_KEY_REQUIRED_PATH_PREFIXES` (no embeber en Vite/mobile) |
| Inventory IDOR mitigation | `InventoryAccessPolicy.require_inventory` → 404 si client mismatch / soft-deleted |
| Admin AI | `require_primary_admin` / `id == "admin"` |

**Riesgos de aislamiento:**

1. Sin `AUTH_*_CLIENT_ID` → platform_admin con acceso global (diseño DEV típico).
2. `ListClientsUseCase.list_all()` **sin filtro por principal** — gap de tenant isolation si se activa `company_admin`.
3. Listado de inventarios carga vía `list_all()` (soft-delete filtrado) **sin filtro client** en el use case de list — mismo gap para company-scoped.
4. Rutas inventory-rooted que usen solo `get_by_id` sin policy pueden filtrar peor que las que usan `InventoryAccessPolicy`.
5. UI admin por username; backend debe (y suele) revalidar — no confiar solo en frontend.

---

## 9. Integraciones externas

| Proveedor | Propósito | Archivos clave | Auth / notas |
|-----------|-----------|----------------|--------------|
| Google Gemini | Identificación LLM | `llm/gemini_*`, registry | API key env |
| OpenAI | LLM | `llm/openai_*` | API key |
| Anthropic | Claude vision/LLM | `llm/anthropic_*` | API key; límites de imagen |
| DeepSeek | Legacy histórico | `llm/deepseek_*` | Remapeado/deprecado para nuevos jobs |
| AWS S3 | Artefactos | `infrastructure/storage/s3_*` | Credenciales AWS / env |
| GCS | Artefactos (DEV OpenCloud) | `gcs_artifact_storage_adapter` | ADC JSON montado |
| SQL Server | Persistencia | `database/sqlserver.py` | ODBC UID/PWD |
| Tesseract / ZBar | OCR / barcodes | `infrastructure/ocr`, `code_scanning` | Nativos en Docker |
| Vercel | Hosting frontend | `frontend/vercel.json` | Git integration `develop` |
| OpenCloud / SSH | Host backend DEV | GHA + docker-compose | Secrets `DEV_HOST`, etc. |
| Prometheus | Métricas/alertas | `/metrics`, `deploy/prometheus` | Auth metrics configurable |

No hay evidencia en código de Stripe, Twilio, WhatsApp u otros pagos/messaging.

---

## 10. Ejecución local

```bash
# Backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install

# Env
cp .env.example .env   # completar SQL + ADMIN_* + AUTH_TOKEN_SECRET (+ LLM keys)

# Arranque recomendado (API + Vite; worker on-demand)
./dev.sh
# o: npm install && npm run dev
```

| Servicio | Puerto típico |
|----------|---------------|
| API | `8000` |
| Vite | `5173` (proxy `/api`, `/auth`, `/health` → 8000) |

**Dependencias:** SQL Server accesible por ODBC; driver Microsoft ODBC 18 en macOS/Linux.  
**Migraciones:** `cd backend && python scripts/db_migrate.py status|validate|apply`  
**Health:** `GET /health`, `GET /ready` (503 si schema incompatible)  
**Mobile:** ver `mobile/README.md` — Expo dev-client, `DINAMIC_API_BASE_URL`, adb reverse.

Carga de env: raíz `.env` luego `backend/.env` (override). Canónico: `backend/src/env_settings/grouped_settings.py`.

---

## 11. Deployment e infraestructura

### DEV (demostrable)

| Componente | Mecanismo |
|------------|-----------|
| Backend | GHA `deploy-dev-opencloud-backend.yml` tras quality gate en push a `develop` → SSH → Docker Compose **solo `api`** en `/opt/dinamic/dinamic-gemini` |
| Migraciones | `dev_deploy_db_migrate.sh` post-up |
| Artefactos | Volumen `data/output` (uid 10001) + GCS secrets bajo `secrets/` |
| Frontend | Vercel Git en `develop` (doc `DEV-VERCEL.md` **referenciada pero ausente**) |
| CI | `develop-quality-gate.yml` (blocking); `main-quality-gate.yml`; frontend/mobile validate |

### Legacy (archivado)

- `deployment/archive/aws-ecs-dev-legacy/` — ECS/ECR
- `deployment/archive/vercel-cli-gha-legacy/` — Vercel CLI GHA

### Producción

**No hay evidencia de pipeline de producción activo.** Workflows: `main` no es prod; “Production will use a dedicated branch later.”

### Riesgos de deploy

- Permisos de volumen `output` (WORKER_LAUNCH_FAILED).
- Secrets GCS faltantes → fail early.
- Refresh tokens no compartidos entre réplicas.
- Schema guard bloquea arranque si versión DB ≠ requerida.

---

## 12. Testing

| Suite | Cantidad aprox. | Herramienta |
|-------|-----------------|-------------|
| Backend | ~591 `test_*.py` | pytest (`pytest.ini`, `pythonpath=backend`) |
| Frontend | ~220 | Vitest |
| Mobile | ~66 | Jest (core/services/integration) |
| Arquitectura | Layering Phase 6 | `backend/tests/architecture/` |
| Prometheus | Alert unit tests | `deploy/prometheus/tests/` |

**Bien cubierto:** use cases application, muchos contratos API, pipeline stages, LLM adapters mocked, mobile upload/scan core, frontend API clients y páginas clave.

**Gaps / riesgos:**

- Pocos tests en `tests/auth` y `tests/jobs` vs complejidad de leases/finalization.
- Integración SQL real limitada (policy de pytest SQL).
- Providers LLM/S3/GCS mayormente mock — no contrato live.
- Coexistencia de tests “stage/epic” root-level con suites layered (posible duplicación).
- Frontend `ProtectedRoute` es placeholder; protección real en `App.tsx`.
- **No inventar % de cobertura** (existe `.coverage`/htmlcov local pero no se trata como métrica oficial del repo).

Comandos: `pytest` (raíz); `cd frontend && npm run typecheck && npm test`; `cd mobile && npm run verify`.

---

## 13. Riesgos y deuda técnica

### CRITICAL

1. **Aislamiento tenant incompleto para `company_admin`:** list clients / list inventories sin filtro por `client_id` del principal — IDOR cross-tenant si se habilita scoping por env.
2. **Auth no multi-usuario:** dos hashes en env; refresh in-memory; no rotación de usuarios/RBAC de producto — inadecuado para multi-tenant real sin trabajo adicional.

### HIGH

3. **`schema.sql` no es snapshot completo de 0097** — faltan ~42 tablas solo creadas en migraciones; instalaciones correctas requieren bootstrap + `apply`. DBs ya en 0097 no están “rotas” por este gap; el riesgo es clean-install mal documentado / mantenimiento DDL duplicado.
4. **Jobs/leases/finalization concurrencia:** claim + on-demand spawn + embedded worker posibles race/doble ejecución si mal configurado; leases fencing existe (0072) pero superficie compleja.
5. **Desalineación auth frontend↔backend:** tipos `administrator` vs `platform_admin`/`company_admin`; gates UI por username string.
6. **Documentación de deploy incompleta:** falta `docs/deployment/DEV-VERCEL.md`; README no documenta OpenCloud/GCS como DEV real.

### MEDIUM

7. Dualidad pipeline híbrido v3 vs track/CLI legacy + `LEGACY_LLM` — riesgo de caminos incorrectos o flags deprecados.
8. Preliminary reconciliation marcada DEPRECATED cuando authoritative ingest está on — confusión mobile.
9. Artefactos legacy local read (`ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED`) — rutas históricas vs durable metadata.
10. Archivos/módulos muy grandes en application services y rutas aisles — mantenimiento y regresiones.
11. Mobile feature-flag heavy; estado “limited rollout” — comportamiento distinto por build.

### LOW

12. `ProtectedRoute` frontend placeholder; redirects legacy acumulados.
13. DeepSeek / Stage-8 SQL bridge flags residuales.
14. `REPO_STRUCTURE.md` desactualizado en detalle (no menciona mobile/contracts/audit).

---

## 14. Áreas sensibles

Modificar con especial cuidado (contratos, datos, dinero/LLM cost, seguridad):

| Área | Rutas |
|------|-------|
| Access / tenancy | `application/services/inventory_access_policy.py`, `api/dependencies.py`, auth |
| Job claim / lease / finalization | `jobs/`, `infrastructure/pipeline/v3_job_executor.py`, migrations 0071–0073, 0037–0041 |
| Persistencia resultados | `persist_aisle_result`, consolidation, `result_evidence` |
| Prompt / LLM adapters | `llm/`, `pipeline/providers/`, prompt composer |
| Artifact storage access | `api/services/v3_stored_artifact_access.py`, storage adapters |
| Soft-delete / merge | migrations 0096–0097, inventory soft-delete use cases, positions merge |
| Migraciones SQL | `database/migrations/versions/` — nunca editar aplicadas a la ligera |
| Mobile upload authority | `mobile/src/features/upload/`, ordered-capture seal, authoritative finalize |
| Position label HMAC / QR | ADR positioning + label signing settings |
| Quality gate / deploy | `.github/workflows/*`, `docs/quality-gate.md` |

---

## 15. Funcionalidades incompletas o ambiguas

- **Producción:** sin pipeline/branch documentado.
- **Multi-usuario / RBAC real:** explícitamente fuera de alcance actual (Jairo temporal).
- **`company_admin` end-to-end:** roles existen; listados globales parecen incompletos.
- **Mobile:** hardening Fase 3+; no “general production” según README mobile.
- **Preliminary reconciliation:** deprecated path coexistiendo con authoritative.
- **CLI track pipeline** vs **hybrid v3 jobs:** ambos viven; el producto web usa hybrid/strategies.
- **Review-queue:** ruta API existe; UI puede estar migrada/redirect (historial DIN-099).
- **Ingestion sessions:** feature frontend marcada legacy/redirect.
- **DOC vs código:** README dice rol JWT `administrator`; código emite `platform_admin`/`company_admin`.
- **Open questions de flags:** muchas feature flags en `grouped_settings.py` — comportamiento depende del `.env` de cada entorno (no inspeccionar secretos reales).

---

## 16. Mapa rápido para futuros agentes

> Si necesitás modificar **X**, empezá inspeccionando **A, B, C**.

| Quiero… | Empezar por |
|---------|-------------|
| Endpoint / contrato API | `backend/src/api/routes/v3/`, `api/schemas/`, `frontend/src/api/`, `frontend/src/constants/v3ApiPaths.ts` |
| Regla de negocio inventario/aisle | `application/use_cases/…`, `domain/inventory|aisle|jobs`, ports |
| Acceso / IDOR / tenant | `inventory_access_policy.py`, `auth/service.py`, `api/dependencies.py` |
| Disparar o debuggear un job | `start_aisle_processing.py`, `aisle_job_launch_service.py`, `jobs/worker.py`, `v3_job_executor.py` |
| Pipeline / prompts / provider | `pipeline/hybrid_inventory_pipeline.py`, `pipeline/stages/`, `llm/`, `pipeline/providers/registry.py` |
| SQL / migración | `schema.sql` + **última migración** en `versions/`, `scripts/db_migrate.py` |
| UI operador | `frontend/src/pages/`, `features/inventories|results|processing`, hooks |
| Captura mobile | `mobile/README.md`, `runtime/bootstrap/createAppServices.ts`, `features/upload`, `database/` |
| Deploy DEV | `docs/deployment/DEV-OPENCLOUD.md`, `backend/docker-compose.yml`, GHA deploy + quality-gate |
| Tests de regresión | espejar carpeta bajo `backend/tests/application|api|…` o `frontend/tests/` |
| Auditorías previas | `audit/`, `review/`, ADRs en `docs/adr/` |
| Config | `.env.example` + `env_settings/grouped_settings.py` (**nunca** commitear `.env`) |

Convenciones del skill del repo: capas limpias; thresholds por config; determinismo UNKNOWN; cambios pequeños.

---

## 17. Preguntas abiertas

Solo lo que **no** se puede cerrar solo con el repo:

1. ¿Cuál es el `.env` real de OpenCloud DEV (provider GCS vs S3, `AUTH_*_CLIENT_ID`, embedded vs on-demand)? — secretos/host no versionados.
2. ¿Existe entorno de staging/prod fuera de este repo (otro org, infra no documentada)?
3. ¿La integración Vercel está ligada al mismo GitHub repo y qué project/env vars tiene? (`DEV-VERCEL.md` ausente).
4. ¿Se usa `company_admin` en algún cliente real hoy, o solo platform_admin?
5. ¿Política operativa para mobile “limited rollout” (quiénes, qué flags de build)?
6. ¿Cobertura de tests exigida en CI (umbral %) y si htmlcov local refleja el gate actual?

---

## Apéndice A — Veredicto de auditoría

| Criterio | Valor |
|----------|--------|
| Contexto reconstruible | Sí, con alta confianza desde código + migraciones + workflows |
| Listo para implementar cambios incrementales | **READY_WITH_RISKS** |
| Bloqueantes antes de features multi-tenant | Aislar listados clients/inventories; alinear tipos auth FE/BE; clean-install = `schema.sql` + migrate apply (no solo bootstrap) |

---

## Apéndice B — Plan/spec implícito del producto (extraído del código + skill)

**In scope v3:** inventories, aisles, assets, jobs, positions/review, clients/suppliers, analytics, capture/ordered-capture, code-scan, positioning labels, mobile sync, soft-delete, merge positions, admin AI/storage, observability.

**Out of scope aparente:** multi-user product admin UI, Redis queues, producción automatizada, DeepSeek para nuevos jobs.

**Compatibilidad:** preservar contratos `/api/v3` y exports; dual read legacy artifacts cuando flag on; JWT legacy `administrator` alias.

---

*Fin de PROJECT_CONTEXT.md*
