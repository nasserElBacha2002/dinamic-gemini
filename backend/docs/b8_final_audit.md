# Cierre Fase B8 — Auditoría Final

**Fecha de auditoría:** 2026-05-04  
**Alcance revisado:** `backend/src/api/routes/v3/`, `backend/src/application/`, `backend/src/pipeline/`, `backend/src/infrastructure/`, `backend/src/llm/` (diagnóstico), más lectura de `backend/docs/b8_code_smells_plan.md`.  
**Método:** análisis estático (Ruff PLR, ripgrep); **sin** modificación de código; **sin** ejecución obligatoria de tests en esta pasada (validación de regresión recomendada en CI / suite completa).

---

## 1. Estado general

| Criterio | Evaluación |
|----------|------------|
| **Cierre B8** | **Parcialmente cerrada** respecto al objetivo amplio “reducir deuda estructural” en todo el alcance histórico de B8: siguen existiendo avisos PLR0911/0912/0913/0915 en las carpetas auditadas (ver §3). |
| **Calidad alcanzada** | **Alta en los focos explícitos** documentados en B8.1–B8.4 (rutas clave, slices de application, `hybrid_inventory_pipeline` en B8.3, ejecutor/mapper/artifact reader en B8.4): refactors con DTOs internos, helpers y separación de fases **sin** cambiar contratos donde el plan lo prohibía. |
| **Consistencia entre subfases** | Alineada con el plan: lo declarado en `b8_code_smells_plan.md` (B8.3 pipeline, B8.4 infrastructure) cuadra con el estado actual de Ruff en esos módulos prioritarios (`hybrid_inventory_pipeline.py` **sin** entrada en el listado PLR actual de `src/pipeline`; `v3_job_executor` / `v3_report_mapper` / `stored_artifact_reader` **sin** PLR en la corrida por paquete). |
| **Regresiones** | **No evaluable** solo con esta auditoría estática. La ausencia de síntomas en Ruff no prueba comportamiento; se recomienda **CI + pytest** tras cualquier cierre formal. |

---

## 2. Evaluación por capa

### API routes (`src/api/routes/v3/`)

| Aspecto | Detalle |
|--------|---------|
| **Estado** | Mejoras documentadas en B8.1 en parte reflejadas: varios archivos citados en B8.0 ya **no** aparecen en el listado PLR (p. ej. `reviews.py`, `review_queue.py`, `positions.py` sin avisos en esta corrida). |
| **Mejoras logradas** | Menor superficie PLR en rutas tocadas; uso habitual de `Depends` para inyectar casos de uso. |
| **Problemas restantes** | **12** avisos PLR (todos **PLR0913** salvo **PLR0911** en `shared.py`): handlers con muchos parámetros (Query/Depends) en `aisles.py`, `assets.py`, `capture_sessions.py`, `inventories.py`, `shared.py`. Patrón dominante: **aridad de función de ruta**, no lógica monolítica suelta. |
| **`except Exception`** | **38** líneas coincidentes (`except Exception`) en este árbol; concentración notable en `capture_sessions.py` y `aisles.py` — muchas rutas siguen el patrón captura amplia + **mapeo HTTP** (`reraise_if_mapped` / similar): clasificación **REVISAR_NO_TOCAR** hasta diseño alternativo (coherente con B8.0). |

### Application (`src/application/`)

| Aspecto | Detalle |
|--------|---------|
| **Estado** | **Cierre B8.2 de hotspots** documentado en `b8_code_smells_plan.md` («B8.2 — Cierre Application»): `materialize_capture_session`, `upload_capture_session_staging_items`, `list_review_queue`, `analytics_aggregation_core` refactorizados sin cambiar contratos públicos ni ports. |
| **Mejoras logradas** | Slices anteriores (`execution_log_enrichment`, G6 preview) + cierre de los cuatro archivos anteriores; recuento PLR del paquete **reducido** (orden ~**36** avisos `PLR0911–PLR0915` en `ruff check src/application`, post-cierre). |
| **Problemas restantes** | **~36** avisos PLR en `application/` (no “cero”): **ports** con PLR0913, `materialize_capture_session_group`, `upload_inventory_visual_references`, export/detail, otros use cases CRUD — deuda **B9** / slices posteriores. |
| **`except Exception`** | **31** líneas (recuento histórico en auditoría); varios **REVISAR_NO_TOCAR** en rollback/cleanup de captura — ver plan B8.2. |

### Pipeline (`src/pipeline/`)

| Aspecto | Detalle |
|--------|---------|
| **Estado** | **B8.3 coherente con el objetivo:** `hybrid_inventory_pipeline.py` **no** figura entre los avisos PLR actuales del paquete (refactor con `_HybridRunParams` y fases). |
| **Mejoras logradas** | Reducción estructural del hot path híbrido; contrato de `process_video` preservado. |
| **Problemas restantes** | **6** avisos: `hybrid_global_analysis_strategy.py` (PLR0915), `run_context.py` (PLR0913), `execution_log.py` (PLR0911, PLR0913), `frame_acquisition_stage.py` (PLR0913, PLR0915). |
| **`except Exception`** | **6** líneas en `pipeline/` (p. ej. `hybrid_inventory_pipeline`, `execution_log`, adapter de estrategia) — revisar caso a caso (logging + propagación). |

### Infrastructure (`src/infrastructure/`)

| Aspecto | Detalle |
|--------|---------|
| **Estado** | **B8.4 cumple en archivos prioritarios:** `v3_job_executor.py`, `v3_report_mapper.py`, `stored_artifact_reader.py` sin entradas PLR en la corrida por paquete. |
| **Mejoras logradas** | DTOs internos (`_V3*`, `_ArtifactByteFetchParams`, etc.), extracción de monitoring y política de descarga; documentado en el plan. |
| **Problemas restantes** | **12** avisos en **otros** módulos: `v3_process_aisle_pipeline_runner.py` (PLR0913 fuerte en `run_hybrid_pipeline`), `v3_job_execution_state.py`, repositorios **SQL/memory** (analytics, positions, capture session, etc.) — alineado con “sin refactor masivo de repositories” en B8.4. |
| **`except Exception`** | **22** líneas; **S3** (`s3_artifact_storage_adapter.py`) y **executor** concentran capturas defensivas de I/O — **riesgo operativo bajo si se estrecha mal**; documentar antes de cambiar. |

### LLM (`src/llm/`) — solo diagnóstico

| Aspecto | Detalle |
|--------|---------|
| **Deuda existente** | **15** avisos PLR: `openai_sdk_adapter.py`, `anthropic_sdk_adapter.py`, `costing.py`, `prompt_traceability.py`, `types.py`, normalización (`numeric_coercion`, `entity_normalizer`), etc. — **alta complejidad** (ramas y sentencias) en adaptadores y costeo. |
| **Alcance B8** | **No** corregido en B8.1–B8.4; previsto como **B8.5** en el plan maestro. |

---

## 3. Smells aún presentes (Ruff PLR0911, PLR0912, PLR0913, PLR0915)

**Comando de referencia:** `ruff check <ruta> --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise`

**Totales por paquete (auditoría 2026-05-04):**

| Paquete | Avisos |
|---------|--------|
| `src/api/routes/v3` | 12 |
| `src/application` | ~36 (post B8.2 cierre hotspots; recalibrar con `ruff`) |
| `src/pipeline` | 6 |
| `src/infrastructure` | 12 |
| `src/llm` | 15 |
| **Suma (alcance informe)** | **~81** (si se usa el nuevo conteo de application) |

### 3.1 API v3 — listado

| Archivo | Regla | Severidad | Recomendación |
|---------|-------|-----------|---------------|
| `aisles.py` | PLR0913 (×3 handlers) | Media | DTO de query/agrupación de `Depends` / parámetros de listado sin cambiar contrato HTTP. |
| `assets.py` | PLR0913 (×2) | Media | Igual. |
| `capture_sessions.py` | PLR0913 (×3) | Media | Igual; archivo con muchos `except Exception` — revisión semántica aparte. |
| `inventories.py` | PLR0913 | Media | Igual. |
| `shared.py` | PLR0911, PLR0913 | Media | Partir `resolve_*` / reducir returns; DTO para params de mapeo. |

### 3.2 Application — síntesis (~36 avisos tras B8.2 cierre hotspots)

**Alta complejidad (PLR0912/0915):** `materialize_capture_session_group.py` (método largo), `upload_inventory_visual_references.py`, y otros use cases de captura no cubiertos por el cierre B8.2. *(Hotspots `materialize_capture_session` y `upload_capture_session_staging_items` abordados en B8.2 — ver plan.)*  
**Aridad (PLR0913):** muchos `__init__` de use cases + **ports** `repositories.py` / `capture_repositories.py` + servicios (`aisle_job_launch_service`, `capture_flow_observability`, query params).  
**Muchos returns (PLR0911):** `position_canonical_view`, `list_inventory_list_items`, `position_traceability`, `list_review_queue` (otros helpers del módulo), etc. *(Cierre B8.2: `issue_bucket_for_position` y funciones de filtro en `list_review_queue` reducidas.)*

### 3.3 Pipeline — listado

| Archivo | Regla | Severidad | Recomendación |
|---------|-------|-----------|---------------|
| `adapters/hybrid_global_analysis_strategy.py` | PLR0915 | Media | Sub-fases en métodos privados. |
| `context/run_context.py` | PLR0913 | Baja–media | Revisar ctor; cuidado con inyección. |
| `execution_log.py` | PLR0911, PLR0913 | Media | Helpers de serialización / writer. |
| `stages/frame_acquisition_stage.py` | PLR0913, PLR0915 | Media | Separar adquisición vs validación. |

### 3.4 Infrastructure — listado

| Archivo | Regla | Severidad | Recomendación |
|---------|-------|-----------|---------------|
| `pipeline/v3_process_aisle_pipeline_runner.py` | PLR0913 (p. ej. 16 args en `run_hybrid_pipeline`) | **Alta** | DTO de invocación (complementa B8.4 en el runner, no en el executor). |
| `pipeline/v3_job_execution_state.py` | PLR0913 | Media | Parámetros de transición de estado como objeto. |
| `repositories/sql_analytics_repository.py` | PLR0912, PLR0915 | Media | CTEs/helpers **sin** cambiar SQL semántico. |
| `repositories/sql_position_repository.py`, `memory_position_repository.py` | PLR0913 | Media | Objeto de criterios de búsqueda. |
| Varios `memory_*` / `sql_*` repositorios | PLR0913 | Baja–media | Misma línea de acción. |

### 3.5 LLM — listado (deuda B8.5)

| Archivo | Regla | Severidad | Recomendación |
|---------|-------|-----------|---------------|
| `openai_sdk_adapter.py` | PLR0912, PLR0915 | **Alta** | Partir manejo de respuesta / streaming. |
| `anthropic_sdk_adapter.py` | PLR0911, PLR0912, PLR0915 | **Alta** | Idem. |
| `costing.py` | PLR0911, PLR0912, PLR0915 | **Alta** | Tabla de reglas o dispatch por proveedor. |
| `prompt_composer/prompt_traceability.py` | PLR0913, PLR0912 | Media | DTO de contexto de prompt. |
| `types.py` | PLR0913 | Media | Agrupar campos en dataclass si no rompe API. |
| `normalization/*.py` | PLR0911 | Baja–media | Early exit / tablas pequeñas. |

---

## 4. Riesgos detectados

| Riesgo | Descripción |
|--------|-------------|
| **Criterio “cero PLR”** | Si B8 se define como “sin avisos PLR en el alcance”, el estado actual (orden **~66** avisos en B8.1–B8.4 carpetas sin LLM, post B8.2) **no** cumple; riesgo de **falsa sensación de cierre**. |
| **Executor vs runner** | B8.4 mejoró `v3_job_executor.py`; el **runner** (`v3_process_aisle_pipeline_runner.py`) sigue con **PLR0913** fuerte — acoplamiento percibido si solo se mira el executor. |
| **Application / captura** | Tras B8.2 cierre, los hotspots `materialize_capture_session` / `upload_capture_session_staging_items` están estructurados; sigue deuda en **otros** use cases de captura (p. ej. `materialize_capture_session_group`) — regresión posible sin tests. |
| **S3 / artifacts** | Muchas capturas amplias en storage — cambiar sin pruebas de integración puede alterar códigos de error observados por API. |
| **Ports con PLR0913** | Cambiar firmas en `ports/repositories.py` por estética PLR **rompe** implementaciones; cualquier diseño debe ser **explícito** (B9 o ADR). |

---

## 5. Deuda técnica para B9 y más allá

| Ítem | Notas |
|------|--------|
| **Ruff masivo / autofix** | Reservado en el plan B8.0 para **B9** (imports, formato, supresiones mecánicas). |
| **`# noqa`** | Presencia acotada en rutas v3 y módulos tocados; revisar que cada `noqa` tenga **justificación** en comentario adyacente o en este doc. |
| **PLR fuera del subárbol v3** | `src/api/dependencies.py` y otros no están en la tabla v3 pero generan muchos **PLR0913** en `ruff check src` global — si CI exige todo `src`, el umbral falla aunque v3 mejore. |
| **`Any`** | Conteo aproximado de líneas con `\bAny\b`: application **111**, pipeline **123**, infrastructure **93**, llm **110**, v3 **12** — **no** es deuda solo de B8; alineación con tipado estricto (B2) es **progresiva**. |
| **`except Exception`** (líneas): v3 **38**, application **31**, pipeline **6**, infrastructure **22**, llm **4** — inventario para refinar en fases futuras. |

---

## 6. Conclusión

### ¿B8 está lista para cerrarse?

- **Como “entrega de subfases B8.1–B8.4”:** **Sí**, con la condición de que el cierre se entienda como **objetivos de cada subfase cumplidos** según `b8_code_smells_plan.md` (rutas priorizadas, slices application, pipeline híbrido, infrastructure ejecutor/mapper/artifacts), con evidencia de refactor estructural en esos módulos.
- **Como “backlog PLR agotado en api/application/pipeline/infrastructure”:** **No** — permanecen del orden de **~66** avisos PLR0911/0912/0913/0915 en esas cuatro raíces (sin contar `llm/`), con **application** ~36 tras cierre B8.2.
- **Incluyendo `llm/` (B8.5):** el cierre **global** de B8 requiere **B8.5** o un **criterio explícito** (p. ej. aceptar deuda remanente documentada hacia B9).

### Qué falta exactamente para “cerrar” B8 de forma estricta

1. **Definir criterio de salida medible:** ¿“cero PLR en `rpath`”, ¿umbral por paquete, o ¿cierre por **hit list** de archivos?
2. **Completar B8.5** en `src/llm/` o documentar exclusión.
3. **Reducir backlog restante** en application (grupo materialize, upload_inventory_visual_references, export/detail, ports) y API v3 (aridad de handlers), más runner de process_aisle e infra repositorios, según prioridad de riesgo.
4. **Validación de regresión:** pipeline de CI + tests relevantes (captura, jobs v3, inventario) — **no** sustituible por solo Ruff.

---

## Anexo — Comandos de reproducción (solo lectura)

```bash
cd backend
.venv/bin/ruff check src/api/routes/v3 --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise
.venv/bin/ruff check src/application --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise
.venv/bin/ruff check src/pipeline --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise
.venv/bin/ruff check src/infrastructure --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise
.venv/bin/ruff check src/llm --select PLR0911,PLR0912,PLR0913,PLR0915 --output-format concise

rg "except Exception" src/api/routes/v3 --glob '*.py' | wc -l
rg "except Exception" src/application --glob '*.py' | wc -l
# …
```

**Nota:** `ruff check src` completo incluye módulos fuera de la tabla B8.0 (p. ej. `api/dependencies.py`, `jobs/`, `database/`) y puede mostrar **cientos** de avisos adicionales; el recuento de **90** de este informe aplica al **alcance de carpetas** listado arriba.
