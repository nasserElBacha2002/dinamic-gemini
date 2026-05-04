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

---

## B8.2 — Correcciones post code review

Post revisión del slice B8.2 (`execution_log_enrichment`, `compute_materialized_capture_session_group_preview`): validaciones puntuales **sin** cambiar comportamiento, **sin** tocar `application/ports/`, y **sin** alterar firmas públicas de use cases.

### `_as_attempt` (`execution_log_enrichment.py`)

- **Validación:** La implementación actual (bool explícito antes que `int`, enteros/floats enteros no negativos, strings parseables a entero ≥ 0) reproduce la tabla solicitada en revisión: `None`/bool → `None`; `-1`/`"-1"` → `None`; `0`/`1`/`"0"`/`" 1 "` → valores esperados; `1.0` → `1`; `1.5` → `None`; `""`/`"   "`/`"abc"` → `None`.
- **Código productivo:** Sin cambios en esta corrección (semántica ya correcta).
- **Tests:** Añadidos en `backend/tests/application/test_execution_log_enrichment.py`: `test_as_attempt_non_negative_semantics` (parametrizado) cubre la tabla anterior; los tests existentes (`test_extract_event_context_from_payload`, `test_extract_attempt_coerces_string`) siguen cubriendo el camino vía `extract_event_context`.

### `except Exception` en `execute` (G6 preview)

- **Validación:** El bloque `except Exception` **no** silencia errores: llama a `logger.exception(...)`, registra métrica de fallo (`record_preview(failed=True)`), emite evento de observabilidad (`emit_capture_flow_event` con `RESULT_FAILED`), y **re-lanza** con `raise` al final. `CaptureSessionGroupIntegrityError` se re-lanza antes sin pasar por este bloque.
- **Decisión:** Se **mantiene** `noqa: BLE001` y el comentario **REVISAR_NO_TOCAR** por diseño: capa de observabilidad uniforme ante fallos inesperados sin alterar el tipo de excepción vista por el llamador.
- **Código productivo:** Sin cambios.

### `# noqa: PLR0913` en `__init__` del use case G6

- **Justificación:** El constructor modela **inyección explícita** de repositorios (`CaptureSessionRepository`, `CaptureSessionGroupRepository`, etc.) y `preview_max_positions`. Agrupar repositorios en un objeto “context” artificial solo para bajar aridad **no** aporta claridad en este slice, **no** modifica ports ni el grafo DI, y mantener parámetros nombrados facilita tests y wiring explícito.
- **Decisión:** Mantener `noqa: PLR0913` en el `__init__` sin cambios de firma.
- **Código productivo:** Sin cambios.

### Contratos y alcance

- **Ports:** No modificados en esta corrección.
- **Contratos públicos:** `execute(...)`, `build_enriched_execution_log`, etc. sin cambios.

### Validación ejecutada (post corrección)

Re-ejecutar localmente / en CI:

- `ruff check` sobre los dos módulos application del slice.
- `mypy` sobre los mismos.
- `pytest backend/tests/application/test_execution_log_enrichment.py` (desde `backend/`: `pytest tests/application/test_execution_log_enrichment.py`).

**Python:** Si el intérprete es **< 3.10**, los tests que importan dominio con `dataclass(kw_only=True)` pueden fallar en **colección**; el test de `_as_attempt` no depende de dominio y debe pasar en cualquier versión soportada por el proyecto.

---

## B8.3 — Pipeline (slice implementado)

**Alcance:** `backend/src/pipeline/` con prioridad en `stages/analysis_stage.py` (revisión) y `hybrid_inventory_pipeline.py` (refactor). **No** se modificaron prompts, providers, orden de etapas, contratos con application, ni schemas de salida.

### `stages/analysis_stage.py`

| Smell (B8.0 / Ruff) | Técnica | Cambios |
|---------------------|---------|--------|
| PLR0912/0913/0915 (mapa) | Ninguna en este slice | `ruff --select PLR0911,PLR0912,PLR0913,PLR0915` no reporta en este archivo: el módulo ya separa logging (`_log_*`), conteos y un `run()` breve. **No** se extrajo lógica adicional para no tocar el hot path del provider sin beneficio medible. |
| Riesgo | — | Partir `run()` en más helpers añadiría indirección cerca de `AnalysisProvider.analyze` sin reducir complejidad estructural real. |

### `hybrid_inventory_pipeline.py`

| Smell (antes) | Técnica | Cambios realizados | Sin tocar / riesgos |
|---------------|---------|--------------------|---------------------|
| PLR0913, PLR0911, PLR0912, PLR0915 en `_run_hybrid` | DTO interno + fases | `@dataclass(frozen=True) _HybridRunParams` agrupa kwargs; `_hybrid_run_params_from_kwargs` (desde `process_video(**kwargs)`) valida claves requeridas e ignora desconocidas; `_hybrid_begin`, `_hybrid_run_through_entity_resolution`, `_hybrid_evidence_reporting_finish` conservan el mismo orden de etapas y los mismos `try`/`except` por stage | `process_video(video_path, mode=..., **kwargs)` **sin cambio** para llamadores; `_run_hybrid(video_path, params)` es método interno — tests que llamaban `_run_hybrid` con kwargs explícitos actualizados a `_HybridRunParams(...)` |
| Contrato | — | `PipelineRunResult`, `_fail_stage`, `_fail_analysis_stage_llm`, helpers de progreso y metadatos sin cambio de semántica |

### Tests

- Actualizados los que invocaban `_run_hybrid` con kwargs: `tests/test_stage_c_stages.py`, `tests/test_frames_2_2_b.py`, `tests/test_stage_2_2_c.py`, `tests/test_stage_2_2_d_llm_provider.py`, `tests/test_e2e_v2_2.py` (import de `_HybridRunParams`).

### Validación B8.3

- `ruff check` (PLR y reglas estándar en archivos tocados): OK tras ajuste de imports (`collections.abc.Mapping`).
- `mypy src/pipeline/hybrid_inventory_pipeline.py`: OK.
- `pytest` sobre tests de pipeline **sin** `test_e2e_v2_2.py`: OK (44 tests en la corrida de referencia).
- **`tests/test_e2e_v2_2.py`:** en intérpretes **< 3.10** pueden fallar en **EvidenceStage** por `int.bit_count()` (uso en `src/evidence/scoring.py` / `src/video/frames.py`) — **no** introducido por B8.3; ejecutar E2E en **Python ≥ 3.10** o corregir compatibilidad de `bit_count` fuera de este slice.

### Otros módulos `src/pipeline/`

- Sin cambios en esta PR; siguen candidatos en siguientes PRs B8.3 menores según el mapa §4 (`execution_log.py`, `frame_acquisition_stage.py`, etc.).

---

## B8.4 — Infrastructure (slice implementado)

**Alcance:** `backend/src/infrastructure/` con prioridad en `pipeline/v3_job_executor.py`, `pipeline/v3_report_mapper.py`, `artifacts/stored_artifact_reader.py`. **No** se alteraron consultas SQL, estructura de tablas, contratos de ports, nombres de campos persistidos, ni el formato de respuestas del mapper (solo estructura de código).

### `pipeline/v3_job_executor.py`

| Smell (antes) | Técnica | Cambios realizados | Sin tocar / riesgos |
|---------------|---------|--------------------|---------------------|
| PLR0913/0915/0912 en cuerpo de `execute` / monolito | DTOs internos + fases + helper de monitoring | `execute` → `_v3_prepare_dispatch` / `_v3_run_job_body`; dataclasess `_V3PreparedJob`, `_V3PipelineInputRequest`, `_V3HybridRunParams` (incl. `pipeline_video_path` para `str` hacia el runner), `_V3FinalizeAfterPipelineParams`, `_V3RunMonitoringRequest`, `_V3WorkerRuntimeHandles`; `_v3_begin_run_monitoring` extrae log + heartbeat; `run_hybrid_pipeline` recibe `video_path` como `video_path or ""` (alineado al tipo `str` del runner — mismo comportamiento que rutas sin vídeo) | `execute(base_path, job_id)`, orden persist → artifacts → `mark_success`, mensajes de error y `except Exception` en persist/upload **sin cambio de semántica** |
| PLR0913 en `__init__` | — | Ya documentado con `# noqa: PLR0913` (DI con muchos repos) |

### `pipeline/v3_report_mapper.py`

| Smell (antes) | Técnica | Cambios realizados | Sin tocar / riesgos |
|---------------|---------|--------------------|---------------------|
| PLR0912 en `_detected_summary`, PLR2004 (`len == 4`) | Helpers + constante | `_BBOX_COORD_COUNT`; `_summary_merge_bbox_lists`, `_summary_merge_optional_string_projections`, `_summary_merge_filename_and_int_projections`; mismos campos en `detected_summary_json` | Lógica de negocio de cantidades (`_qty_from_entity`) sin cambios |
| PLR0912/0915 en `map_hybrid_report_to_domain` | Contexto + una entidad por función | `_HybridMapContext`, `_map_single_hybrid_entity`, `_first_bbox_json`; bucle externo solo acumula listas | Firma pública de 7 args conservada; `# noqa: PLR0913` en la entrada pública (contrato estable). `run_dir` sigue en la firma y se asigna a `_` (no se usaba en el cuerpo previo) — **sin** cambio de datos emitidos |
| PLR0913 (7 args públicos) | `noqa` explícito | Evita romper `persist_aisle_result` y tests que llaman con kwargs |

### `artifacts/stored_artifact_reader.py`

| Smell (antes) | Técnica | Cambios realizados | Sin tocar / riesgos |
|---------------|---------|--------------------|---------------------|
| PLR0915 en `load_artifact_content_from_provider_meta` | DTO + funciones de módulo | `_ArtifactByteFetchParams`, `_artifact_get_object_bytes`, `_artifact_download_bytes_via_temp`, `_artifact_fetch_bytes_by_policy` reproducen el mismo árbol de decisión (HEAD, hard_max, mem_threshold, tempfile) | Mensajes HTTP/texto de `StoredArtifactAccessError`, logging y `except Exception` en HEAD/get/download **iguales** |

### `storage/s3_artifact_storage_adapter.py`

| Smell | Técnica | Cambios |
|-------|---------|--------|
| PLR (mapa) | Ninguno en este slice | `ruff --select PLR` no reporta en este archivo; sin cambios.

### Validación B8.4

- `ruff check --select PLR` en archivos tocados: OK.
- `mypy` en `v3_job_executor.py`, `v3_report_mapper.py`, `stored_artifact_reader.py`: OK.
- `pytest tests/infrastructure/pipeline/test_v3_report_mapper_and_persist.py` y suite `tests/infrastructure/pipeline/test_v3_job_executor_*.py` (phase5, input_resolution, coordination, analysis_context): OK.

### Repositories / otros

- **Sin** refactor masivo de repositories en este slice (prioridad ejecutor + mapper + artifact reader).

### Próximo paso sugerido (B8.5)

- Si el plan global lo define: **B8.5 — LLM / providers** (code smells en capa de llamadas a modelo, prompts ya acotados por contrato), o continuar infrastructure puntual si el mapa PLR marcará algún `Sql*Repository` en un slice menor dedicado.
