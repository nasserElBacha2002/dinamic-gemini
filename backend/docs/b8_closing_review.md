# Code review final — Cierre B8

**Fecha:** 2026-05-04  
**Alcance:** Backend — Code smells estructurales (fases B8.0–B8.5).  
**Tipo de revisión:** Crítica; lectura de código + auditoría estática; **sin** modificación de código productivo en esta pasada (solo este documento).

**Referencias:** `b8_code_smells_plan.md`, `b8_final_audit.md` (la auditoría previa queda **parcialmente obsoleta** en § LLM tras B8.5; este informe actualiza cifras y decisión).

---

## 1. Resumen ejecutivo

La fase **B8 cumplió su objetivo principal**: reducir complejidad en **hotspots acordados** por capa (rutas críticas, use cases prioritarios, pipeline híbrido, ejecutor/mapper/artifact reader, capa LLM) mediante **refactors locales** (helpers, DTOs internos, separación por pasos) **sin** romper contratos HTTP públicos, puertos de aplicación, orden funcional del pipeline ni semántica de persistencia/LLM donde el plan lo prohibía.

**Lo que B8 no pretendía abarcar:** eliminar **todo** aviso Ruff PLR en `backend/src` ni erradicar `except Exception` / `Any`. Esa continuación es explícitamente el mandato de **B9 (Ruff / lint por lotes)**.

**Estado de cierre:** **B8 se considera cerrada con deuda controlada** (ver §7). El backend **está en condiciones de avanzar a B9**, asumiendo que B9 asumirá el remanente de PLR, `noqa`, excepciones amplias y refino de tipos.

**Punto de atención crítica:** el comando `ruff check backend/src --select PLR0911,PLR0912,PLR0913,PLR0915` aún reporta **~118** hallazgos en el **árbol completo** de `src` (incluye paquetes **fuera** del alcance explícito B8, p. ej. `view_selection/`, `video/`, `reid/`, etc.). Esto **no invalida** el cierre de B8; delimita el trabajo de B9.

---

## 2. Estado por subfase

| Subfase | Estado | Archivos / ámbito principal | Resultado | Pendientes |
|---------|--------|------------------------------|-----------|------------|
| **B8.0** | Cerrada | `b8_code_smells_plan.md` | Mapa y criterios; sin código | — |
| **B8.1** | Cerrada con deuda | `api/routes/v3/` | Menor PLR en rutas tocadas; `Depends` y helpers | **12** PLR0911/0913 en v3; muchos `except Exception` + mapeo HTTP (patrón documentado) |
| **B8.2** | Cerrada con deuda | `application/` (hotspots: materialize, staging, review queue, analytics, etc.) | Hotspots priorizados reducidos; contratos/ports estables en refactors documentados | **~36** PLR en el paquete; ports y más use cases sin barrer |
| **B8.3** | Cerrada con deuda | `pipeline/` (`hybrid_inventory_pipeline`, contexto, etc.) | `hybrid_inventory_pipeline` sin PLR en corrida actual; fases y `_HybridRunParams` alineados al plan | **6** PLR en `execution_log`, `frame_acquisition`, `hybrid_global_analysis_strategy`, `run_context` |
| **B8.4** | Cerrada con deuda | `infrastructure/` (ejecutor, mapper, artifact reader, etc.) | Focos prioritarios sin PLR; DTOs internos documentados | **12** PLR en runner, repositorios, job state, etc. |
| **B8.5** | Cerrada | `llm/` | **0** avisos PLR0911–0915 en `ruff check src/llm`; adaptadores y costeo refactorizados sin cambiar fórmulas ni contratos I/O | `gemini_client.py`: excepciones amplias / complejidad no atacada; tipado `Any` frecuente (típico de JSON/SDK) |

---

## 3. Evaluación por capa

### API routes (`src/api/routes/v3/`)

- **Contratos:** No hay evidencia en esta revisión de cambio de paths, query params ni schemas de respuesta **como objetivo de B8**; los refactors apuntaron a aridad de handlers y helpers (`shared`, listados). El OpenAPI sigue derivado de FastAPI; riesgo residual: cualquier regresión solo es verificable con **tests de contrato / snapshot OpenAPI** en CI (recomendado en B9).
- **Complejidad:** La deuda dominante es **PLR0913** (muchos `Query`/`Depends`) y **`shared.py`** (PLR0911); coherente con “DTO de ruta” pospuesto.
- **`except Exception`:** Concentración en `capture_sessions.py` y `aisles.py` con **reraise / mapeo HTTP** — aceptado en plan B8.0 como **REVISAR_NO_TOCAR** hasta rediseño.

### Application (`src/application/`)

- **Ports:** Los refactors documentados **no** cambian firmas de puertos públicos como estrategia; los **PLR0913** restantes en `ports/` y use cases son **deuda B9** o slices futuros.
- **Hotspots:** Los archivos explícitamente cerrados en el plan muestran **reducción real** de ramas/sentencias; el paquete completo **no** está “plano” — es esperable.

### Pipeline (`src/pipeline/`)

- **Orden de ejecución:** Los cambios descritos en el plan preservan etapas y contrato de `process_video` / metadatos; no se detectó en revisión estática un “reordenamiento silencioso” (validación definitiva: tests de pipeline).
- **Prompts / providers / schemas:** Fuera de cambio funcional en B8.3 según reglas; adaptación LLM detallada en B8.5.
- **Restos PLR:** principalmente **estrategia global analysis**, **execution log**, **frame acquisition**, **run_context** — volumen bajo (6).

### Infrastructure (`src/infrastructure/`)

- **SQL / persistencia:** B8.4 se centró en **refactor estructural** del ejecutor, mapper y lectura de artefactos; **no** en reescritura de consultas. Riesgo de regresión: **bajo** si los tests de integración cubren ejecutor y mapper (recomendación: mantenerlos verdes en CI).
- **S3 / I/O:** `except Exception` defensivos — documentados en auditorías previas; estrechar tipos en B9 con cuidado operativo.

### LLM (`src/llm/`)

- **Prompts / requests / parsing / costes:** Cierre B8.5 afirma **equivalencia** de comportamiento; corrección explícita del `raise ... from e` inválido en respuesta no-objeto (OpenAI) mejora **semántica de excepciones encadenadas** sin cambiar códigos de error expuestos.
- **`costing.py`:** Lógica extraída a helpers; **fórmulas y snapshots** deben seguir gobernados por `tests/llm/test_llm_costing.py`.
- **Capa completa:** `ruff` PLR **limpia** en `llm/`; el único “hueco” conocido es **`gemini_client.py`** (no barrido como los adaptadores OpenAI/Anthropic en cuanto a smells/excepciones).

---

## 4. Riesgos detectados

### Críticos

- **Ninguno identificado** que impida **cerrar B8** bajo el criterio acordado (hotspots + sin ruptura intencional de contratos). La ausencia de regresión funcional **no** está probada solo con esta revisión estática.

### Medios

- **PLR remanente (~66** en los cinco paquetes B8; **~118** en `backend/src` entero): riesgo de **deuda técnica acumulada** si B9 se retrasa; mitigación = lotes priorizados + CI.
- **`except Exception`** en rutas y jobs: riesgo de **enmascarar bugs** si el mapeo HTTP o el log no son exhaustivos; ya conocido y parcialmente aceptado.
- **Python &lt; 3.10** en algunos entornos: sintaxis y tipado (union `|` vs `Optional`) pueden divergir; B9 debe alinear CI con la versión mínima soportada del producto.

### Bajos

- **`noqa` y `Any`:** Legibilidad y mantenimiento a largo plazo; no bloquean B9.
- **Documentación:** `b8_final_audit.md` refleja estado **pre-B8.5** en la tabla LLM; usar **este documento** como decisión de cierre actualizada.

---

## 5. Deuda aceptada para B9

| Categoría | Detalle |
|-----------|---------|
| **PLR restantes** | **api/routes/v3:** 12 · **application:** 36 · **pipeline:** 6 · **infrastructure:** 12 · **llm:** 0 · **Suma alcance B8:** **66**. Además **~52** PLR en resto de `backend/src` (total ~118). |
| **`noqa` aceptados** | Dispersos: constructores estables (`llm/types`), APIs públicas (`prompt_traceability`), rutas/repositorios — revisión caso por caso en B9. |
| **Broad exceptions** | Decenas de coincidencias `except Exception` en los cinco paquetes; **S3**, **capture_sessions**, **worker**, **executor** — priorizar por criticidad y tests. |
| **`Any` / tipado** | Uso extendido en JSON/metadata (`execution_log_enrichment`, `costing`, `v3_report_mapper`, adapters LLM, etc.) — B9 puede activar reglas progresivas (`ANN`, refinamiento gradual). |
| **Lint mecánico** | F401, formato, imports — explícitamente **B9** según plan maestro. |

---

## 6. Validación ejecutada

Comandos (desde raíz del repo; herramienta: `python3 -m ruff`):

```bash
python3 -m ruff check backend/src --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: Found 118 errors (árbol completo backend/src)

python3 -m ruff check backend/src/llm --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: All checks passed!

python3 -m ruff check backend/src/api/routes/v3 --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: Found 12 errors

python3 -m ruff check backend/src/application --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: Found 36 errors

python3 -m ruff check backend/src/pipeline --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: Found 6 errors

python3 -m ruff check backend/src/infrastructure --select PLR0911,PLR0912,PLR0913,PLR0915
# Resultado: Found 12 errors
```

**Búsquedas auxiliares (ripgrep):**

- `except Exception` — presencia sustancial en rutas v3 (especialmente `capture_sessions.py`), application, infraestructura (S3, executor), pipeline y llm (`gemini_client`, `anthropic` retry loop).
- `# noqa` — concentración en application + algunos archivos infra/API/llm (justificación variable).
- `Any` — uso frecuente en capas de metadata/JSON y adapters; no auditado línea a línea en esta revisión.

**Tests / mypy:** Esta revisión **no** sustituye CI. Se recomienda gate en B9: `pytest` por dominio, `mypy` sobre paths críticos, y verificación de versión Python en CI &gt;= la documentada para el proyecto.

**Limitación de entorno:** Ejecutar tests con `PYTHONPATH=.` desde `backend/` (no `PYTHONPATH=src`) evita sombrear el módulo estándar `io` con el paquete local `src/io`.

---

## 7. Decisión final

| Pregunta | Respuesta |
|----------|-----------|
| **¿B8 queda cerrada?** | **Sí**, como fase de **refactor estructural focalizado** con deuda residual explícita (no como “cero smells en todo `src`”). |
| **¿Lista para avanzar a B9?** | **Sí.** B9 debe absorber el lint por lotes, PLR remanente y limpieza mecánica. |
| **¿Qué condición mínima faltaría si no estuviera lista?** | No aplica con la decisión anterior. Si el equipo exigiera **cero PLR en los cinco paquetes** antes de B9, **no** se cumple hoy (**66** avisos); esa condición sería **post-B9** o un **B8-bis** no alineado con el alcance original. |

**Opción del informe de estado:** **B) B8 CERRADA CON DEUDA CONTROLADA — lista para B9.**

---

## 8. Recomendación concreta para B9

1. **Congelar** expectativa: B9 es el dueño del **resto de Ruff** y del **backend/src** completo (~118 PLR), no solo los cinco paquetes.
2. **Orden sugerido:** (a) reglas mecánicas seguras, (b) PLR en rutas con DTOs de query, (c) application ports/use cases de menor riesgo, (d) `gemini_client` + repos SQL masivos.
3. **No estrechar `except Exception` en rutas** sin tests de error HTTP y sin revisión de `reraise_if_mapped`.
4. **Actualizar** `b8_final_audit.md` en un PR menor si se desea **una sola fuente numérica** (opcional; este archivo ya refleza el post-B8.5).
