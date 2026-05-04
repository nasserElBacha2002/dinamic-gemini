# Fase B8.0 — Preparación y clasificación de code smells (backend)

**Estado:** mapa de auditoría para B8.1–B8.5. **No implica correcciones** en B8.0.

**Fuentes de datos (solo lectura, B8.0):** `ripgrep` sobre `except Exception` / `except BaseException`; `ruff check` con reglas `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915`, `F401` sobre los cinco paquetes en alcance. **Ruff masivo / autofix** queda para **B9**; aquí solo se usó para **inventariar** (sin `--fix`).

**Conteo aproximado (PLR anteriores en alcance):** ~115 avisos; `F401` en el momento del análisis: **0** en esos paths (MECÁNICO bajo en imports no usados en este slice).

---

## 1. Objetivo

**B8** (fases B8.1–B8.5) busca **reducir deuda estructural** (complejidad, argumentos, ramas, sentencias, excepciones demasiado amplias) **sin cambiar comportamiento funcional** observable: mismas reglas de negocio, mismos contratos HTTP, mismos flujos de pipeline/LLM.

B8.0 **no corrige código**; define **dónde** y **cómo** atacar en implementaciones posteriores, por capa, con riesgo y fase sugerida.

---

## 2. Alcance revisado

Solo se consideran (código y, en B8.0, documentación bajo `backend/docs/`):

| Paquete | Ruta | Fase B8 sugerida |
|---------|------|------------------|
| API v3 | `backend/src/api/routes/v3/` | **B8.1** |
| Application | `backend/src/application/` | **B8.2** |
| Pipeline | `backend/src/pipeline/` | **B8.3** |
| Infrastructure | `backend/src/infrastructure/` | **B8.4** |
| LLM | `backend/src/llm/` | **B8.5** |

Queda **fuera** de este mapa: `tests/`, `scripts/`, raíz de `src/` no listada, frontend, CI, hooks.

---

## 3. Criterio de clasificación

| Categoría | Descripción | Típico en B8.x |
|-----------|-------------|----------------|
| **MECÁNICO** | Import/variable no usada, formato, supresiones obsoletas (sin tocar lógica). | B9 si masivo; si aparece aislado en B8, mismo archivo que el refactor. |
| **REFACTOR_LOCAL** | Extraer helper privado, reducir ramas/sentencias en una función, early-return; sin nuevo contrato público. | B8.1–B8.5 según módulo. |
| **DTO_O_AGRUPACIÓN** | Demasiados argumentos (`PLR0913`): agrupar en `NamedTuple` / dataclass interno / objeto de contexto. | Tras revisión de llamadores; cuidado en **ports** y **constructores**. |
| **EXCEPCIÓN_AMPLIA** | `except Exception` / `BaseException` sin criterio claro; riesgo de tragar errores o enmascarar fallos. | Sustituir por tipos concretos, `raise ... from` o dejar explícito el “best-effort” con log. |
| **REVISAR_NO_TOCAR** | Smell real pero **cambiar ahora** implica riesgo de comportamiento o contrato: p. ej. `except Exception` + `reraise_if_mapped` en rutas, `noqa: BLE001` documentado, limpieza S3 con “no fallar el request”. | Documentar; posible fase dedicada o B9. |

**Severidad relativa (guiada por Ruff + lectura):**

- **Alta:** `PLR0915` fuerte (p. ej. >50–80 sentencias) o `PLR0912` muy por encima del umbral + `except Exception` en hot path.
- **Media:** `PLR0913` (6–10 args) o `PLR0911` (returns) en servicios críticos.
- **Baja:** umbral ligeramente superado, o funciones ya acotadas con buenos tests.

**Riesgo de cambio:** bajo (helper local) → medio (DTO en use case) → alto (ports, `v3_job_executor`, adaptadores LLM, mapeo de reportes).

---

## 4. Hallazgos por módulo (síntesis)

Las tablas listan **archivos priorizados** y **tipos de smell**; no repiten los ~115 avisos PLR uno a uno. Detalle: ejecutar en el repo (solo lectura):

`ruff check <path> --select PLR0911,PLR0912,PLR0913,PLR0915`

### B8.1 — API routes (`src/api/routes/v3/`)

| Archivo | Smell (típico) | Categoría | Riesgo | Acción recomendada | Fase |
|---------|----------------|-----------|--------|-------------------|------|
| `capture_sessions.py` | Muchos `except Exception` + `reraise_if_mapped`; varias rutas con `PLR0913` | EXCEPCIÓN_AMPLIA* / DTO_O_AGRUPACIÓN | Medio | Revisar si se puede acotar excepciones **sin** romper mapeo HTTP; agrupar parámetros de query en dataclass de ruta | B8.1 |
| `aisles.py` | `except Exception` + `PLR0913` en varios handlers | Similar | Medio | Igual; extraer solo si no altera wiring FastAPI | B8.1 |
| `positions.py` | `PLR0913` (p. ej. 14 args en `list_aisle_positions`) | DTO_O_AGRUPACIÓN | Medio | Objeto de filtros/paginación ya alineado con Query params | B8.1 |
| `review_queue.py` | `PLR0913` (~14 args) | DTO_O_AGRUPACIÓN | Medio | DTO de query interno para la ruta | B8.1 |
| `reviews.py` | `PLR0911` + `PLR0913` | REFACTOR_LOCAL / DTO | Medio | Partir por acción o agrupar params | B8.1 |
| `shared.py` | `PLR0911` / `PLR0913` (`resolve_normalized_asset_path`, `aisle_to_response`, etc.) | REFACTOR_LOCAL | Medio–alto | Helpers ya parcialmente extraídos en B7; no regresar contratos | B8.1 |
| `inventories.py`, `assets.py` | `PLR0913`, `except Exception` | Mixto | Bajo–medio | Params de listado ya parcialmente externalizados (B7.5/B7.4) | B8.1 |
| `analytics_api.py` | `except Exception` | EXCEPCIÓN_AMPLIA | Medio | Tipar excepciones de dominio/servicio | B8.1 |

\* Muchos `except Exception` en rutas existen **para** delegar en `reraise_if_mapped` → clasificación **REVISAR_NO_TOCAR** hasta diseñar alternativa que preserve **textos y códigos** de error.

---

### B8.2 — Application (`src/application/`)

| Archivo | Smell (típico) | Categoría | Riesgo | Acción recomendada | Fase |
|---------|----------------|-----------|--------|-------------------|------|
| `use_cases/compute_materialized_capture_session_group_preview.py` | `PLR0912`, `PLR0915` altos | REFACTOR_LOCAL | Alto | Sub-funciones por fase (preview, validación, agregación) | B8.2 |
| `use_cases/materialize_capture_session.py` | `PLR0912`, `PLR0915`, `PLR0913` | REFACTOR_LOCAL | Alto | Idem; varios `except Exception` con `noqa` → documentar o estrechar | B8.2 |
| `use_cases/materialize_capture_session_group.py` | `PLR0915`, `PLR0913` | REFACTOR_LOCAL | Alto | Extraer pasos de materialización | B8.2 |
| `use_cases/upload_capture_session_staging_items.py` | `PLR0912`, `PLR0915` | REFACTOR_LOCAL + EXCEPCIÓN_AMPLIA | Alto | Menos ramas por tipo de ítem; cleanup en `try/finally` donde aplique | B8.2 |
| `use_cases/list_review_queue.py` | `PLR0911` (returns) | REFACTOR_LOCAL | Medio | Tabla de estrategias o early exit por modo | B8.2 |
| `use_cases/export_inventory_results.py`, `get_position_detail.py` | `PLR0913` (muchos deps en ctor) | DTO_O_AGRUPACIÓN / REVISAR | Medio–alto | Agrupar repos en “context” solo si no rompe DI | B8.2 |
| `services/execution_log_enrichment.py` | `PLR0911`, `PLR0913` | REFACTOR_LOCAL | Medio | Funciones por etapa de enriquecimiento | B8.2 |
| `services/analytics_aggregation_core.py` | `PLR0911` | REFACTOR_LOCAL | Medio | Partir por métrica o reduce | B8.2 |
| `ports/repositories.py`, `ports/capture_repositories.py` | `PLR0913` en interfaces | DTO_O_AGRUPACIÓN | **Alto** | **REVISAR_NO_TOCAR** en primera pasada: cambiar firma de port afecta toda la capa | B8.2 (diseño) |
| Varios use cases “CRUD” posición/producto | `PLR0913` (6–7 args en `execute`) | DTO_O_AGRUPACIÓN | Medio | Command objects ya existen en parte; unificar patrón | B8.2 |

---

### B8.3 — Pipeline (`src/pipeline/`)

| Archivo | Smell (típico) | Categoría | Riesgo | Acción recomendada | Fase |
|---------|----------------|-----------|--------|-------------------|------|
| `hybrid_inventory_pipeline.py` | `PLR0913` (17 args), `PLR0912`, `PLR0915`, `except Exception` | REFACTOR_LOCAL + EXCEPCIÓN_AMPLIA | Alto | Objeto de contexto de corrida; no alterar orden de etapas ni artefactos | B8.3 |
| `adapters/hybrid_global_analysis_strategy.py` | `PLR0915`, `except Exception` | REFACTOR_LOCAL | Alto | Extraer subpasos de estrategia | B8.3 |
| `execution_log.py` | `PLR0911`, `PLR0913`, `except Exception` | REFACTOR_LOCAL | Medio | Helpers de serialización / flush | B8.3 |
| `context/run_context.py` | `PLR0913` | DTO_O_AGRUPACIÓN | Medio | Campos ya agrupados; revisar si sobran parámetros en ctor | B8.3 |
| `stages/frame_acquisition_stage.py` | `PLR0915`, `PLR0913` | REFACTOR_LOCAL | Medio | Dividir adquisición vs validación | B8.3 |

---

### B8.4 — Infrastructure (`src/infrastructure/`)

| Archivo | Smell (típico) | Categoría | Riesgo | Acción recomendada | Fase |
|---------|----------------|-----------|--------|-------------------|------|
| `pipeline/v3_job_executor.py` | `PLR0915` (~145), `PLR0912` (~24), `PLR0911`; varios `except Exception` | REFACTOR_LOCAL + EXCEPCIÓN_AMPLIA | **Muy alto** | Partir en funciones por fase (enqueue, persist, artefactos); excepciones: distinguir persist vs orchestration **sin** cambiar estados observables | B8.4 |
| `pipeline/v3_process_aisle_pipeline_runner.py` | `PLR0913` (p. ej. 16 args), `PLR0915` | REFACTOR_LOCAL | Alto | Context object para runner | B8.4 |
| `pipeline/v3_report_mapper.py` | `PLR0912`, `PLR0915`, `PLR0913` | REFACTOR_LOCAL | Alto | Mapeo por bloques de schema | B8.4 |
| `artifacts/stored_artifact_reader.py` | `PLR0915`, `except Exception` | REFACTOR_LOCAL + EXCEPCIÓN_AMPLIA | Alto | Lectura por operación; errores de storage más específicos donde sea seguro | B8.4 |
| `storage/s3_artifact_storage_adapter.py` | Múltiples `except Exception` | EXCEPCIÓN_AMPLIA / REVISAR | Alto | Muchos son defensivos I/O; documentar “no propagar” vs **REVISAR_NO_TOCAR** | B8.4 |
| `repositories/sql_analytics_repository.py` | `PLR0915`, `PLR0912` | REFACTOR_LOCAL | Medio | CTEs/subconsultas en helpers | B8.4 |
| `repositories/sql_position_repository.py`, `memory_position_repository.py` | `PLR0913` (10 args) | DTO_O_AGRUPACIÓN | Medio–alto | Filtrado como objeto de criterios | B8.4 |

---

### B8.5 — LLM (`src/llm/`)

| Archivo | Smell (típico) | Categoría | Riesgo | Acción recomendada | Fase |
|---------|----------------|-----------|--------|-------------------|------|
| `costing.py` | `PLR0912`, `PLR0915`, `PLR0911`, `except Exception` | REFACTOR_LOCAL | Alto | Tablas de precios por modelo/proveedor; **no** cambiar fórmulas sin tests de golden | B8.5 |
| `openai_sdk_adapter.py` | `PLR0912`, `PLR0915` muy altos | REFACTOR_LOCAL | Alto | Extraer parseo de streaming vs batch | B8.5 |
| `anthropic_sdk_adapter.py` | `PLR0912`, `PLR0915`, `PLR0911`, `except Exception` | REFACTOR_LOCAL | Alto | Bloques por endpoint API Anthropic | B8.5 |
| `gemini_client.py` | `except Exception` (grep) | EXCEPCIÓN_AMPLIA | Alto | Mapear errores SDK | B8.5 |
| `prompt_composer/prompt_traceability.py` | `PLR0913`, `PLR0912` | DTO_O_AGRUPACIÓN | Medio | Agrupar metadatos de traza | B8.5 |
| `normalization/numeric_coercion.py`, `entity_normalizer.py` | `PLR0911` | REFACTOR_LOCAL | Medio | Casos por tipo | B8.5 |
| `types.py` | `PLR0913` | DTO_O_AGRUPACIÓN | Medio | Revisar constructores de mensajes | B8.5 |

---

## 5. Priorización sugerida (orden de ataque en B8.1+)

1. **B8.1 (`api/routes/v3`)** — Alto impacto visual y bajo riesgo si se limita a helpers y DTOs de query: `positions.py`, `review_queue.py`, `reviews.py`; luego `capture_sessions.py` / `aisles.py` (muchas rutas, patrón `except Exception` uniforme).
2. **B8.2 (application)** — Use cases de capture materialization / staging y `execution_log_enrichment` (complejidad y ramas).
3. **B8.4 (infrastructure)** — `v3_job_executor.py` y `stored_artifact_reader.py` como núcleo operativo; coordinar con tests de integración antes de tocar excepciones.
4. **B8.3 (pipeline)** — `hybrid_inventory_pipeline.py` depende de estabilidad de etapas; refactor solo con tests de pipeline/regresión.
5. **B8.5 (llm)** — `costing.py` y adaptadores SDK: alto riesgo de drift de costes/comportamiento; último o con golden files.

**Archivos “hot” transversales:** `shared.py` (B8.1), `v3_job_executor.py` (B8.4), `hybrid_inventory_pipeline.py` (B8.3).

---

## 6. Qué queda fuera de B8.0

- **No** se corrige código productivo en B8.0 salvo este documento (y metadatos de docs si aplica).
- **No** CI/CD, pre-push, pipelines ni quality gates nuevos.
- **No** Ruff/eslint masivo ni autofix global (**B9**).
- **No** cambio de contratos públicos HTTP, schemas, códigos de status, textos de error wire, prompts, ni proveedores LLM “por limpieza”.
- **No** cambio de reglas de negocio encubierto como “refactor”; cada PR B8.x debe mantener comportamiento verificable.

---

## 7. Definition of Done — B8.0

- [x] Mapa de smells por paquete y archivo prioritario.
- [x] Cada categoría MECÁNICO / REFACTOR_LOCAL / DTO_O_AGRUPACIÓN / EXCEPCIÓN_AMPLIA / REVISAR_NO_TOCAR aplicada en ejemplos.
- [x] Fases B8.1–B8.5 alineadas con rutas de carpeta.
- [x] Priorización explícita y riesgos (ports, executor, LLM).
- [x] Sin modificación de comportamiento en B8.0.
- [x] Listo el contexto para **prompt de B8.1** (empezar por `api/routes/v3`, archivos de alta densidad de `PLR0913` y rutas largas).

---

## 8. Nota sobre validación técnica (B8.0)

Comandos **solo lectura** usados para este inventario:

```bash
cd backend
rg "except Exception|except BaseException" src/api/routes/v3 src/application src/pipeline src/infrastructure src/llm
ruff check src/api/routes/v3 src/application src/pipeline src/infrastructure src/llm \
  --select PLR0911,PLR0912,PLR0913,PLR0915,F401 --output-format=concise
```

Re-ejecutar antes de B8.1 para números actualizados tras merges.

---

## 9. Prompt sugerido para iniciar B8.1

> Implementar **B8.1** solo en `backend/src/api/routes/v3/`: reducir `PLR0913` en rutas con muchos parámetros Query/Path agrupando en dataclasses internos o dependencias FastAPI sin cambiar URLs ni schemas; donde `except Exception` solo envuelve `reraise_if_mapped`, marcar **REVISAR_NO_TOCAR** o acotar excepciones **solo** si los tests API y el mapping de errores lo confirman. Entregar PR pequeño por archivo o por subcarpeta (p. ej. `positions.py` + `review_queue.py` primero). Sin Ruff autofix masivo; alinear con `backend/docs/b8_code_smells_plan.md`.

---

## 10. B8.1 — API routes (implementado)

**Objetivo:** Reducir complejidad en endpoints prioritarios sin cambiar contratos HTTP ni comportamiento.

### `positions.py`

| Smell abordado | Técnica | Sin tocar / notas |
|----------------|---------|-------------------|
| PLR0913 (muchos params en `list_aisle_positions`) | Query params agrupados en `_ListAislePositionsQuery` vía `Depends(_list_aisle_positions_query_dep)` | Los `Query()` permanecen en la función de dependencia (mismos nombres y descripciones OpenAPI). |
| PLR0913 / statements en `list_aisle_positions` | Helper `_position_summaries_for_list` | — |
| PLR0913 en `get_position_detail` | `_PositionDetailQuery` vía `Depends(_position_detail_query_dep)` | — |
| Statements en detalle | `_build_position_detail_response` | — |
| `except Exception` + `mapped_http_exception` | Comentario `# REVISAR_NO_TOCAR` | No se estrecharon excepciones (preserva mapeo HTTP). |
| PLR0913 en `_list_aisle_positions_query_dep` | `# noqa: PLR0913` + comentario | Un `Query()` por parámetro público; aridad fijada por el contrato FastAPI/OpenAPI. |

### `review_queue.py`

| Smell abordado | Técnica | Sin tocar / notas |
|----------------|---------|-------------------|
| PLR0913 en `list_review_queue_positions` | `_ReviewQueueRouteQuery` + `Depends(_review_queue_query_dep)`; el handler queda con `use_case` y `rq` | — |
| Statements | `_to_review_queue_query`, `_review_queue_items` | — |
| PLR0913 en `_review_queue_query_dep` | `# noqa: PLR0913` + comentario | Misma razón: un parámetro Query por query string documentado. |

### `reviews.py`

| Smell abordado | Técnica | Sin tocar / notas |
|----------------|---------|-------------------|
| PLR0913 (muchos `Depends` en `submit_review_action`) | `_ReviewActionDependencies` + `Depends(get_review_action_dependencies)` | — |
| PLR0911 (múltiples `return` en el handler) | `_dispatch_review_action` conservando la misma cadena if/elif | Comportamiento idéntico. |
| PLR0913 en `get_review_action_dependencies` | `# noqa: PLR0913` + comentario | Una inyección por use case según DI actual. |

### Archivos no tocados en este slice

- **`capture_sessions.py`**, **`aisles.py`**: dejar para un siguiente PR de B8.1 si se confirma el mismo patrón.

### Validación B8.1

- `ruff check` sobre los tres archivos: **OK**.
- `mypy` sobre los tres archivos: **OK**.
- `pytest tests/api`: **documentar** si el entorno local usa Python 3.9 y falla la carga de la app por tipos en `auth/config`; ejecutar en CI / Python ≥ 3.10.

---

## 11. Próximo paso (tras B8.2 slice actual)

Continuar en `backend/src/application/` con los use cases pendientes del §4 (`materialize_capture_session`, `upload_capture_session_staging_items`, `list_review_queue`, `analytics_aggregation_core`, etc.), con PRs pequeños y tests de application en **Python ≥ 3.10** (el dominio usa `dataclass(kw_only=True)`).

---

## 12. B8.2 — Application (slice implementado)

**Alcance de este slice:** `services/execution_log_enrichment.py` y `use_cases/compute_materialized_capture_session_group_preview.py`. **No** se modificó `application/ports/`. Contratos HTTP y de use case públicos se conservaron; solo se añadieron DTOs/helpers **privados** o se documentaron supresiones puntuales.

### `services/execution_log_enrichment.py`

| Smell detectado (antes) | Técnica aplicada | Cambios realizados | Sin tocar / riesgos |
|---------------------------|------------------|--------------------|---------------------|
| PLR0911 (`_as_attempt`) | Ramificación con acumulador `out` + `return` único final | `_non_negative_int_or_none`; `_as_attempt` delega sin múltiples salidas tempranas | — |
| PLR0913 (`_available_job_attempt_execution_lists`) | DTO interno frozen | `_AvailableJobAttemptExecutionListsInputs` | — |
| PLR0913 (`_build_enriched_execution_log_core`) | DTO interno frozen | `_EnrichedExecutionLogCoreParams`; núcleo recibe un solo objeto | Firmas públicas `build_enriched_execution_log` / `build_enriched_aisle_aggregated_execution_log` sin cambios |
| PLR0913 (`build_enriched_aisle_aggregated_execution_log`) | `# noqa: PLR0913` | Parámetros del sobre multi-job explícitos para estabilidad de llamadores API | Riesgo bajo: supresión documentada en este plan |
| `broad-except` en `_as_nonempty_str` (sesión previa) | `except (TypeError, ValueError, AttributeError)` | Ya aplicado; conversión a string defensiva | — |

### `use_cases/compute_materialized_capture_session_group_preview.py`

| Smell detectado (antes) | Técnica aplicada | Cambios realizados | Sin tocar / riesgos |
|---------------------------|------------------|--------------------|---------------------|
| PLR0913 (`_classify_g6_preview_status`) | DTO interno frozen | `_G6PreviewStatusInputs`; una sola entrada al clasificador | Semántica de estados `empty` / `partial` / `ready` inalterada |
| PLR0913 (`__init__` del use case) | `# noqa: PLR0913` | Inyección de repos + `preview_max_positions` sin cambiar firma | Patrón DI estable; no agrupar repos en un “context” en este slice |
| PLR0915 / responsabilidades mezcladas en `_execute_inner` (sesión previa) | Helpers `_g6_*`, `_G6WorkState` | Carga, join, distinción de ítems, conteos y resultado separados | — |
| `except Exception` en `execute` | **REVISAR_NO_TOCAR** | `noqa: BLE001` + métricas/emisión en fallo inesperado | Cambiar tipos aquí podría ocultar fallos no instrumentados |
| E501 | Ajuste de docstrings y tipo de retorno partido | Líneas ≤ 100 caracteres | Texto funcional de documentación ligeramente acortado en el docstring del módulo |

### Validación B8.2 (slice)

- `ruff check … --select PLR0911,PLR0912,PLR0913,PLR0915,E501` en los dos archivos: **OK**.
- `mypy` en los dos archivos: **OK**.
- `pytest tests/application/test_execution_log_enrichment.py`: **OK** (entorno local).
- Tests que importan dominio con `dataclass(kw_only=True)`: requieren **Python ≥ 3.10**; si `python3` apunta a 3.9, la recolección falla antes de ejecutar aserciones (limitación de entorno, no del diff).

### Archivos de application aún priorizados (no tocados en este slice)

- `use_cases/materialize_capture_session.py`
- `use_cases/upload_capture_session_staging_items.py`
- `services/analytics_aggregation_core.py`, `use_cases/list_review_queue.py`, export/detail con deps altos, etc. (mapa §4 B8.2)
