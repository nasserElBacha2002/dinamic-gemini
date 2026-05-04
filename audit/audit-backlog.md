# Backlog de bugs y vulnerabilidades

## B0 — Revalidación Bandit backend (pre-B3), 2026-05-04

**Objetivo:** Estado real antes de la fase B3 (Bandit HIGH/MEDIUM). **Sin cambios de código productivo.**

**Comando:** `cd backend && bandit -r src` (salida: `audit/raw/backend-bandit-b3-current.json`, `audit/raw/backend-bandit-b3-current.txt`).  
**Herramienta:** Bandit 1.9.4 · Python 3.13 (venv repo).

**Totales (coinciden con corrida 2026-04-29):** 59 hallazgos · **1 HIGH** · **35 MEDIUM** · **23 LOW** · ~45k LOC.

### Clasificación por familia (estado B0)

| Familia / ID | Archivos / notas | Estado B0 | Comentario |
|--------------|------------------|-----------|------------|
| **B324** MD5 “weak hash” | `src/app.py:161` (`run_hash` para `run_id`) | **YA_CORREGIDO** (B3.1) | Aplicado `usedforsecurity=False`; `run_id` mantiene formato. |
| **B608** SQL dinámico / string SQL | 35 ocurrencias: `migrations/service.py` (4), `sql_analytics_repository.py` (12), `sql_capture_session_repository.py` (3), `sql_final_count_repository.py` (2), `sql_job_repository.py` (6), `sql_normalized_label_repository.py` (2), `sql_position_repository.py` (3), `sql_product_record_repository.py`, `sql_raw_label_repository`, `sql_source_asset_repository` (1 c/u) | **CONFIRMADO** (lista estática) | Riesgo SQLi real: **PENDIENTE_DE_REPRODUCIR** por consulta (muchas rutas usan parámetros ODBC). B3: revisar cada construcción; posibles **FALSO_POSITIVO** donde solo hay concatenación de fragmentos con placeholders. |
| **B101** `assert` en producción | 9 (`capture_assignment_preview`, `compare_aisle_runs`, `compare_many_aisle_runs`, `export_aisle_benchmark`, `v3_execution_artifacts_service`, `v3_job_executor`, `costing`, `multi_provider_analysis_execution`) | **FALSO_POSITIVO** / bajo | Regla advierte `-O`; asserts como invariantes internas — fuera del alcance típico B3 salvo política explícita. |
| **B106** “hardcoded password” | `auth/service.py` `token_type="bearer"` (2 líneas) | **FALSO_POSITIVO** | Literal estándar OAuth; no es secreto. |
| **B110** `try/except: pass` | `sqlserver.py`, `sqlserver_resolution.py`, `v3_job_executor.py`, `dev_reset_local_jobs.py`, `worker.py`, `hybrid_inventory_pipeline.py` | **CONFIRMADO** | Revisar en B3 si el silenciamiento es aceptable o debe loguearse/narrow except. |
| **B404** `subprocess` import | `on_demand_worker_launch_service.py` | **CONFIRMADO** | Revisión contextual B3 (uso real de subprocess). |
| **B603** `subprocess` call | mismo módulo ~L43 | **CONFIRMADO** | Revisión contextual B3 (argumentos fijos vs usuario). |
| **B112** `try/except: continue` | `dev_reset_local_jobs.py` | **CONFIRMADO** | Baja severidad; revisar en B3 si aplica. |
| **B311** `random` | `anthropic_sdk_adapter.py` | **CONFIRMADO** / probable **FALSO_POSITIVO** | Uso no criptográfico habitual; validar en B3. |

**Resumen:** Ningún hallazgo marcado como **YA_CORREGIDO** en esta corrida (baseline sin parches B3). Evidencia cruda: `audit/raw/backend-bandit-b3-current.json` y `.txt`.

**Actualización AUD-004:** Métricas vigentes alineadas con esta evidencia; enlaces preferentes a los archivos `backend-bandit-b3-current.*`.

---

## B3 — Seguridad backend (Bandit)

### B3.1 — HIGH B324 + triage B608 (2026-05-04)

**Alcance:** Sin CI/CD, sin hooks, sin refactor masivo de repos.

#### Parte A — B324 (`backend/src/app.py`)

- **Estado:** Corregido en código.
- **Uso:** `run_hash` solo para sufijo no secreto del `run_id` CLI (`timestamp` + 8 hex); no integridad ni MAC.
- **Cambio:** `hashlib.md5(..., usedforsecurity=False)` — formato de salida **sin cambio** (sigue siendo 8 hex de MD5).
- **Validación local:** `python -m bandit -r src/app.py` (sin severidad HIGH en este archivo).

#### Parte B — Triage B608 (35 ocurrencias)

Cada fila = un disparo Bandit B608. Clasificación: **FP-P** = FALSO_POSITIVO_PARAMETRIZADO (valores vía `?`); **DC** = DINÁMICO_CONTROLADO (solo constantes internas / enums / límites numéricos acotados); **NRM** = NECESITA_REFACTOR_MINIMO (sustituir f-string por SQL estático o `text()` documentado).

| Archivo | Línea | Hallazgo (resumen) | Clasificación | Riesgo real | Acción propuesta (B3.2+) |
|--------|-------|-------------------|---------------|-------------|-------------------------|
| `src/database/migrations/service.py` | 88 | `cur.execute(f"""` CREATE TABLE / IF NOT EXISTS; nombre tabla `{_MIGRATION_TABLE}` | DC | Nulo (tabla fija `schema_migrations`) | Opcional: SQL literal sin interpolación o `# nosec B608` con justificación |
| `src/database/migrations/service.py` | 135 | `SELECT version FROM {_MIGRATION_TABLE} …` + `?` service | FP-P | Nulo | Misma línea |
| `src/database/migrations/service.py` | 150 | `SELECT TOP 1 version FROM {_MIGRATION_TABLE}` + `?` | FP-P | Nulo | Misma línea |
| `src/database/migrations/service.py` | 172 | `INSERT` / `IF NOT EXISTS` sobre `{_MIGRATION_TABLE}` + parámetros | FP-P | Nulo | Misma línea |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 201 | `sql_positions = f"""` SELECT agregados | FP-P / DC | Bajo | Revisar que `WHERE`/joins usen solo listas de condiciones con `?` (típico en este módulo) |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 219 | `sql_reviews = f"""` … | FP-P / DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 271 | `sql_avg_job_processing = f"""` + `job_proc_where` por join de condiciones | DC | Bajo | Verificar origen de cada fragmento en `job_proc_conditions` |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 363 | `sql = f"""` métricas + `where_j` | DC | Bajo | Condiciones construidas con `?` desde filtros de aplicación |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 391 | `sql_daily_reviews = f"""` | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 422 | `sql_daily_jobs = f"""` | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 519 | `sql = f"""` inventario/aisle scope | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 619 | `sql = f"""` review actions | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 673 | `sql = f"""` duración jobs | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 697 | `sql = f"""` low confidence + umbral `LOW_CONFIDENCE_THRESHOLD` | DC | Bajo | Umbral constante config |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 787 | `sql = f"""` buckets | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_analytics_repository.py` | 853 | `sql = f"""` CTE scoped_actions | DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_capture_session_repository.py` | 164 | `COUNT` + `NOT IN ({placeholders})` estático para `_OPEN_STATUS_EXCLUSION` | FP-P | Nulo | Lista de exclusión fija en código; placeholders `?` |
| `src/infrastructure/repositories/sql_capture_session_repository.py` | 206 | `count_sql = f"SELECT … WHERE {where_sql}"` — `where_sql` armado solo con fragmentos `col = ?` / `IN (?)` | FP-P | Bajo | IDs/fechas vía parámetros; no concatenar input crudo |
| `src/infrastructure/repositories/sql_capture_session_repository.py` | 207 | `list_sql = f"""` mismo `where_sql` + OFFSET/FETCH | FP-P | Bajo | Idem |
| `src/infrastructure/repositories/sql_final_count_repository.py` | 154 | `SELECT … WHERE … ? ?` + `{extra_sql}` de `_sql_job_predicate` (solo `""`, `IS NULL`, o `AND job_id = ?`) | FP-P | Nulo | Sin SQL arbitrario desde API |
| `src/infrastructure/repositories/sql_final_count_repository.py` | 215 | `DELETE … ? ?` + `{extra_sql}` mismo helper | FP-P | Nulo | Idem |
| `src/infrastructure/repositories/sql_job_repository.py` | 244 | `f"SELECT {_JOB_SELECT_FIELDS} … WHERE id = ?"` | FP-P | Nulo | `_JOB_SELECT_FIELDS` constante de columnas |
| `src/infrastructure/repositories/sql_job_repository.py` | 255 | `f""" SELECT TOP 1 {_JOB_SELECT_FIELDS} … ? ?` | FP-P | Nulo | Idem |
| `src/infrastructure/repositories/sql_job_repository.py` | 274 | `TOP ({n})` con `n` entero acotado 1–500 | DC | Nulo | No es cadena usuario |
| `src/infrastructure/repositories/sql_job_repository.py` | 288 | `f"SELECT {_JOB_SELECT_FIELDS} ORDER BY …"` sin user input en texto | FP-P | Nulo | Lista columnas fija |
| `src/infrastructure/repositories/sql_job_repository.py` | 298 | CTE + `IN ({placeholders})` + params | FP-P | Bajo | `target_ids` como `?` |
| `src/infrastructure/repositories/sql_job_repository.py` | 358 | `UPDATE … WHERE status IN ({stale_statuses})` — valores desde enum Python | DC | Nulo | No es SQLi HTTP; opcional NRM: construir IN con `?` por status |
| `src/infrastructure/repositories/sql_normalized_label_repository.py` | 179 | `f""" SELECT … WHERE inventory_id = ? AND aisle_id = ?` | FP-P | Nulo | Parámetros |
| `src/infrastructure/repositories/sql_normalized_label_repository.py` | 203 | `f"DELETE … ? ?` | FP-P | Nulo | Parámetros |
| `src/infrastructure/repositories/sql_position_repository.py` | 243 | Rama join: `sql = f"""` SELECT … | FP-P / DC | Bajo | Columnas/joins fijos; revisar rama |
| `src/infrastructure/repositories/sql_position_repository.py` | 253 | Rama sin join: `sql = f"""` | FP-P / DC | Bajo | Idem |
| `src/infrastructure/repositories/sql_position_repository.py` | 292 | `get_by_id` / fetch por id | FP-P | Bajo | Params |
| `src/infrastructure/repositories/sql_product_record_repository.py` | 175 | `f""" SELECT … WHERE position_id = ?` | FP-P | Nulo | Param |
| `src/infrastructure/repositories/sql_raw_label_repository.py` | 174 | `f""" SELECT … WHERE inventory_id = ? AND aisle_id = ?` | FP-P | Nulo | Params |
| `src/infrastructure/repositories/sql_source_asset_repository.py` | 237 | `f"""` agregación por `aisle_id` + `?` | FP-P | Bajo | Params |

**Resumen triage:** Ningún B608 clasificado como **RIESGO_REAL** explícito sin auditoría más profunda; la mayoría **FP-P** o **DC**. Prioridad B3.2: (1) `sql_job_repository` L358 si se desea eliminar f-string; (2) `sql_analytics_repository` revisión muestral de filtros; (3) migraciones con tabla constante — bajo impacto.

**DoD B3.1:** B324 corregido; tabla anterior completa; tests/revalidación manual recomendada en el Python del proyecto.

---

## Críticos

### AUD-001 - Fallos masivos en pruebas backend core (API/use-cases/pipeline)
- Área: Backend
- Herramienta: Pytest
- Severidad: Crítico
- Archivo/Ruta: `backend/tests/api/`, `backend/tests/application/use_cases/`, `backend/tests/infrastructure/pipeline/`
- Descripción: La corrida backend reporta 94 tests fallidos sobre 1785, con afectación transversal de flujos operativos.
- Riesgo: Regresiones funcionales en operaciones principales de inventario y procesamiento.
- Evidencia:
  - `audit/raw/backend-pytest.txt`
- Recomendación futura: Plan de estabilización por dominios y smoke tests de regresión por flujo.
- Estado: Pendiente

### AUD-002 - Fallos masivos en pruebas frontend de pantallas operativas
- Área: Frontend
- Herramienta: Vitest
- Severidad: Crítico
- Archivo/Ruta: `frontend/tests/ExecutionLogPanel.test.tsx`, `frontend/tests/CompareRunsPage.test.tsx`, `frontend/tests/MetricsPage.test.tsx`, `frontend/tests/InventoryDetailPage.test.tsx`
- Descripción: La corrida frontend registra 86 tests fallidos en 19 archivos.
- Riesgo: Alto riesgo de regresión visible en UX y flujos de operador.
- Evidencia:
  - `audit/raw/frontend-vitest.txt`
- Recomendación futura: Estabilizar suites por prioridad de negocio antes de endurecer gate.
- Estado: Pendiente

## Altos

### AUD-003 - Errores de tipado backend en contratos críticos
- Área: Backend
- Herramienta: Mypy
- Severidad: Alto
- Archivo/Ruta: `backend/src/api/routes/v3/`, `backend/src/application/`, `backend/src/pipeline/`, `backend/src/llm/`
- Descripción: 80 errores de tipado en 35 archivos, incluyendo retornos incompatibles, símbolos faltantes y tipos ambiguos.
- Riesgo: Fallos en runtime y degradación de contratos internos.
- Evidencia:
  - `audit/raw/backend-mypy.txt`
- Recomendación futura: Corregir por capas empezando por rutas y casos de uso.
- Estado: Pendiente

### AUD-004 - Hallazgos de seguridad backend con severidad alta/media
- Área: Backend
- Herramienta: Bandit
- Severidad: Alto
- Archivo/Ruta: `backend/src/infrastructure/repositories/`, `backend/src/database/migrations/`, `backend/src/app.py`, otros (ver B0)
- Descripción: 59 hallazgos (1 HIGH, 35 MEDIUM, 23 LOW), destacando SQL dinámico (B608) y manejo de excepciones (B110).
- Riesgo: Superficie de ataque y ocultamiento de errores.
- Evidencia:
  - **Actual (pre-B3):** `audit/raw/backend-bandit-b3-current.json`, `audit/raw/backend-bandit-b3-current.txt`
  - Histórico: `audit/raw/runs/20260429-190315/backend-bandit.json`
- Recomendación futura: Fase B3 — HIGH (B324) y MEDIUM (B608) con triage; ver clasificación en sección **B0** arriba.
- Estado: Pendiente (revalidado 2026-05-04)

### AUD-005 - Vulnerabilidades moderadas en dependencias frontend
- Área: Frontend
- Herramienta: npm audit
- Severidad: Alto
- Archivo/Ruta: `frontend/package-lock.json`
- Descripción: 7 vulnerabilidades moderadas, principalmente en cadena Vite/Vitest/esbuild/postcss/yaml.
- Riesgo: Riesgo de seguridad en tooling de build/test y CI.
- Evidencia:
  - `audit/raw/frontend-npm-audit.json`
- Recomendación futura: Plan de upgrade controlado con validación de compatibilidad.
- Estado: Pendiente

### AUD-006 - Violación de límites de arquitectura backend (application -> api)
- Área: Arquitectura backend
- Herramienta: Import boundaries audit
- Severidad: Alto
- Archivo/Ruta: `backend/src/application/services/position_traceability.py`
- Descripción: Se detecta regla FAIL en boundaries: capa application importa componente de `src.api`.
- Riesgo: Acoplamiento inverso y erosión de DIP.
- Evidencia:
  - `audit/raw/backend-import-boundaries.txt`
- Recomendación futura: Reubicar dependencia a puerto/servicio de capa intermedia.
- Estado: Pendiente

### AUD-007 - Complejidad alta en orquestación backend
- Área: Arquitectura backend
- Herramienta: Radon / complexity
- Severidad: Alto
- Archivo/Ruta: `backend/src/pipeline/hybrid_inventory_pipeline.py`, `backend/src/pipeline/stages/analysis_stage.py`
- Descripción: Se detectan funciones con grado D y múltiples C en pipeline/orquestación.
- Riesgo: Mayor probabilidad de defectos, baja testabilidad y mantenimiento costoso.
- Evidencia:
  - `audit/raw/backend-complexity.txt`
- Recomendación futura: Refactor por subresponsabilidades y límites de etapa.
- Estado: Pendiente

### AUD-008 - Code smells backend estructurales (too-many-*, imports no usados)
- Área: Arquitectura backend
- Herramienta: Pylint
- Severidad: Alto
- Archivo/Ruta: `backend/src/` (múltiples módulos)
- Descripción: Alta recurrencia de `too-many-arguments`, `too-many-branches`, `too-many-statements`, `unused-import`.
- Riesgo: Baja cohesión, mayor acoplamiento y dificultad de evolución segura.
- Evidencia:
  - `audit/raw/backend-code-smells.txt`
- Recomendación futura: Remediación incremental por módulos críticos.
- Estado: Pendiente

### AUD-009 - Code smells frontend en hooks React (set-state-in-effect)
- Área: Arquitectura frontend
- Herramienta: ESLint / frontend code smells
- Severidad: Alto
- Archivo/Ruta: `frontend/src/components/CreateAisleDialog.tsx`, `frontend/src/components/ExecutionLogPanel.tsx`, `frontend/src/components/ui/ImageViewer.tsx`
- Descripción: Findings de `react-hooks/set-state-in-effect` y dependencias faltantes.
- Riesgo: Renders en cascada, efectos no deterministas y errores de estado.
- Evidencia:
  - `audit/raw/frontend-eslint.txt`
  - `audit/raw/frontend-code-smells.txt`
- Recomendación futura: Reestructurar efectos y derivaciones de estado.
- Estado: Pendiente

### AUD-010 - Complejidad extrema en frontend (componentes/servicios muy grandes)
- Área: Arquitectura frontend
- Herramienta: Complexity audit
- Severidad: Alto
- Archivo/Ruta: `frontend/src/features/analytics/MetricsPage.tsx`, `frontend/src/api/client.ts`, `frontend/src/pages/AislePositionsPage.tsx`
- Descripción: Archivos >300 líneas (algunos >1000) y alta densidad condicional.
- Riesgo: Mantenibilidad baja y mayor tasa de defectos.
- Evidencia:
  - `audit/raw/frontend-complexity.txt`
- Recomendación futura: Separar por módulos/hook/controller view-model.
- Estado: Pendiente

## Medios

### AUD-011 - Deuda de lint backend de gran volumen
- Área: Backend
- Herramienta: Ruff
- Severidad: Medio
- Archivo/Ruta: `backend/` (global)
- Descripción: 3545 errores de lint con alto ruido técnico acumulado.
- Riesgo: Dificulta revisiones y detección de issues críticos.
- Evidencia:
  - `audit/raw/backend-ruff.txt`
- Recomendación futura: Plan por lotes (autofix seguro + revisión manual por reglas).
- Estado: Pendiente

### AUD-012 - Acoplamiento frontend components -> API/fetch directo
- Área: Arquitectura frontend
- Herramienta: Import boundaries audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/components/` (múltiples)
- Descripción: Se detectan imports/uso directo de API/fetch desde componentes UI.
- Riesgo: Mezcla de responsabilidades y menor reutilización/testabilidad.
- Evidencia:
  - `audit/raw/frontend-import-boundaries.txt`
- Recomendación futura: Consolidar lógica en hooks/adapters de capa intermedia.
- Estado: Pendiente

### AUD-013 - Señales de lógica pesada en rutas API backend
- Área: Arquitectura backend
- Herramienta: Import boundaries audit (heurística R3)
- Severidad: Medio
- Archivo/Ruta: `backend/src/api/routes/v3/aisles.py`, `inventories.py`, `shared.py`, `assets.py`, `capture_sessions.py`
- Descripción: Rutas extensas con alta ramificación, sospecha de lógica de negocio en capa API.
- Riesgo: Baja cohesión en controllers y mayor acoplamiento.
- Evidencia:
  - `audit/raw/backend-import-boundaries.txt`
- Recomendación futura: Extraer coordinación de negocio a casos de uso/servicios application.
- Estado: Pendiente

### AUD-014 - Hallazgos heurísticos SOLID/GRASP backend
- Área: Arquitectura backend
- Herramienta: SOLID/GRASP audit
- Severidad: Medio
- Archivo/Ruta: `backend/src/` (global)
- Descripción: Señales de SRP, DIP y acoplamiento requieren validación manual.
- Riesgo: Deuda arquitectónica progresiva si no se gobierna por reglas.
- Evidencia:
  - `audit/raw/backend-solid-grasp-audit.md`
- Recomendación futura: Definir políticas de import boundaries como código y checks de arquitectura.
- Estado: Pendiente

### AUD-015 - Hallazgos heurísticos SOLID/React frontend
- Área: Arquitectura frontend
- Herramienta: SOLID/React audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/` (global)
- Descripción: Señales de componentes con múltiples responsabilidades y acoplamiento UI-lógica.
- Riesgo: Escalabilidad limitada y mayor costo de evolución por feature.
- Evidencia:
  - `audit/raw/frontend-solid-react-audit.md`
- Recomendación futura: Definir contratos UI/hooks/services y criterios de composición.
- Estado: Pendiente

### AUD-016 - Código muerto potencial frontend (exports no usados)
- Área: Arquitectura frontend
- Herramienta: ts-prune
- Severidad: Medio
- Archivo/Ruta: `frontend/src/` (múltiples módulos)
- Descripción: Alto volumen de exports reportados como no usados o usados solo localmente.
- Riesgo: Complejidad accidental y superficie de mantenimiento innecesaria.
- Evidencia:
  - `audit/raw/frontend-dead-code.txt`
- Recomendación futura: Clasificar hallazgos por criticidad y limpiar de forma incremental.
- Estado: Pendiente

### AUD-017 - Duplicación frontend sin métrica robusta instalada
- Área: Arquitectura frontend
- Herramienta: Duplicación audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/` (componentes con patrones repetidos)
- Descripción: `jscpd` no instalado; fallback textual detecta familias de componentes repetibles.
- Riesgo: Duplicación no cuantificada con precisión y posible deuda de UI.
- Evidencia:
  - `audit/raw/frontend-duplication.txt`
- Recomendación futura: habilitar `jscpd` en entorno y re-ejecutar medición formal.
- Estado: Pendiente

### AUD-018 - Limitaciones en auditoría useEffect (falsos negativos posibles)
- Área: Frontend
- Herramienta: useEffect audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/`
- Descripción: Se detectan 46 usos, pero varios patrones complejos quedan en 0 por heurística textual.
- Riesgo: Subdetección de riesgos reales en side-effects.
- Evidencia:
  - `audit/raw/frontend-useeffects-audit.md`
- Recomendación futura: mejorar scanner con AST o reglas de lint específicas.
- Estado: Pendiente

### AUD-019 - Auditoría de manejo de errores sin priorización por impacto
- Área: Frontend
- Herramienta: Error handling audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/`, `frontend/tests/`
- Descripción: 100 archivos con patrones de error, sin clasificación por criticidad ni contexto de usuario.
- Riesgo: Backlog ruidoso y baja accionabilidad inmediata.
- Evidencia:
  - `audit/raw/frontend-error-handling-audit.md`
- Recomendación futura: categorizar por capa y por impacto UX/operativo.
- Estado: Pendiente

## Bajos

### AUD-020 - Warning recurrente de entorno npm (devdir)
- Área: Tooling
- Herramienta: npm
- Severidad: Bajo
- Archivo/Ruta: entorno local npm
- Descripción: `npm warn Unknown env config "devdir"` aparece en múltiples reportes.
- Riesgo: Ruido en logs y confusión operativa.
- Evidencia:
  - `audit/raw/frontend-eslint.txt`
  - `audit/raw/frontend-typecheck.txt`
  - `audit/raw/frontend-npm-audit.json`
  - `audit/raw/frontend-vitest.txt`
- Recomendación futura: estandarizar configuración npm de entorno local/CI.
- Estado: Pendiente

### AUD-021 - pipaudit backend con limitación de paquete local no publicado
- Área: Dependencias backend
- Herramienta: pip-audit
- Severidad: Informativo
- Archivo/Ruta: `backend` package metadata
- Descripción: No hay CVEs conocidas, pero el paquete local `dinamic-gemini` no es auditable en PyPI.
- Riesgo: Visibilidad parcial del riesgo de dependencias propias.
- Evidencia:
  - `audit/raw/backend-pip-audit.json`
- Recomendación futura: mantener SBOM y control de dependencias directas/transitivas en CI.
- Estado: Pendiente

## Informativos

### AUD-022 - Typecheck frontend sin errores en corrida auditada
- Área: Frontend
- Herramienta: Typecheck
- Severidad: Informativo
- Archivo/Ruta: `frontend/src/`
- Descripción: `tsc --noEmit` ejecuta correctamente en la evidencia actual.
- Riesgo: Sin riesgo inmediato detectado en tipado TS.
- Evidencia:
  - `audit/raw/frontend-typecheck.txt`
- Recomendación futura: sostener gate de typecheck y monitorear regresiones.
- Estado: Pendiente

## Falsos positivos / a validar

- Bandit `B608` puede marcar SQL dinámico seguro con placeholders parametrizados.
- `ts-prune` incluye casos “used in module” que requieren validación manual antes de eliminar.
- Auditorías heurísticas SOLID/GRASP y SOLID/React no prueban violación formal por sí solas.
- Auditorías por patrones textuales (`useEffect`, error handling, reusable components) pueden omitir casos reales o sobredetectar ruido.
