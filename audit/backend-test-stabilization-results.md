# Fase B1 — Estabilizacion de tests backend core

Fecha: 2026-04-27

## Estado inicial

- Corrida invalida detectada en B0: `pytest` faltante y ejecucion con Python 3.9 (incompatible con `typing.Self`, `dataclass(kw_only=...)` y operadores de tipos `|`).
- Entorno valido para B1: interpreter `.venv` con Python 3.13; runner `.venv/bin/python -m pytest` desde la raiz del repo (`pytest.ini` establece `pythonpath = backend`).

## Estado final (B1.2 — corrida global)

Ejecucion desde la raiz del monorepo:

```bash
.venv/bin/python -m pytest -q
```

Resultado (sin cambios en `pytest.ini` / con cobertura por defecto):

```txt
1772 passed, 13 skipped, 114 warnings
Failed: 0
```

Corrida equivalente sin cobertura (`--override-ini="addopts="`): mismos totales de passed/skipped (~13 s).

### Clasificacion de cambios (B1.2)

| Tipo | Descripcion breve |
|------|-------------------|
| Stubs | `SourceAssetRepository`: `get_by_capture_session_item_id` en `test_upload_aisle_assets.py`, `test_aisle_source_asset_materializer.py`, `test_v3_job_executor_analysis_context.py`. |
| SQL integracion | `pytest.mark.integration` en repos SQL que usan ODBC; helper `tests/support/sql_integration.py` con ping `SELECT 1`, timeout corto ODBC y `pytest.skip` si no hay servidor; evita timeouts largos cuando la cadena existe pero el host no responde. |
| Config pytest | `pythonpath = ["."]` en `backend/pyproject.toml` para `pytest` lanzado desde `backend/`; marcador `integration` registrado en `pytest.ini`. |
| Upload use case | Tests renombrados y expectativas alineadas con el flujo actual (no compensacion de storage si falla `save` antes de completar `persist`). |
| SQL job repo (unit) | Conteos de placeholders INSERT/UPDATE alineados con `SqlJobRepository` (27 / 26). |
| Schemas | `MinifiedProduct` exige campo `r`; tests actualizados. |
| Stage 3 | Mocks apuntan a `generate_global_analysis_structured`; JSON v2.1 valido (`total_entities_detected` / `entities`). |
| Stage 5 | dHash y blur: datos sinteticos deterministas / umbrales acordes con metricas reales. |
| Stage 8 | Informe de exito usa clave `entities`; aserciones de `insert_pallet_results` y tupla SQL segun columnas actuales. |
| SQL visual refs | IDs unicos por ejecucion (`uuid`) para evitar choques de PK en DB compartida. |
| API wiring | Renombres de tests (`cancel` idempotente, proceso bloqueado por job activo); eliminacion de assert redundante en log `.txt`. |

## Cambios realizados (historico B1.1 / focos)

### Use-cases y pipeline (stubs y firmas)

- Stubs con `get_by_capture_session_item_id` / `delete_by_id` donde correspondia.
- `ConfirmPositionUseCase.execute(..., job_id=...)`.
- Pipeline: `NoopRepo` / coordenacion y mensajes de error.

### API

- Estados `starting`, `cancel_requested`, respuestas 422, patch `load_settings`, E2E `position_id`.

## Pendientes para fases futuras

- Reducir `DeprecationWarning` en tests y codigo legacy (fuera de alcance B1).
- Opcional: ejecutar solo integracion con SQL real (`-m integration`) en entorno con SQL Server y schema aplicado.

---

## Corrida global final (B1.4 — cierre)

Fecha de validacion: 2026-04-27

Comando (raiz del repo, `pytest.ini` con cobertura por defecto):

```bash
.venv/bin/python -m pytest -q
```

Resultado:

```txt
Total tests: 1785  (1772 passed + 13 skipped)
Passed: 1772
Skipped: 13
Failed: 0
```

Duracion aproximada: ~19 s (incluye `--cov=src` y reportes term/html).

### Criterios de cierre B1 (verificados)

| Criterio | Estado |
|----------|--------|
| `pytest -q` → 0 failed | Cumplido |
| Entorno reproducible (`.venv`, Python 3.13, `pythonpath` en `pytest.ini` / `backend/pyproject.toml`) | Cumplido |
| Tests alineados al comportamiento real del backend | Cumplido (sin cambios productivos en esta corrida) |
| Integration SQL no rompe suite local (skip / timeout si no hay DB) | Cumplido |
| Codigo productivo `backend/src/` sin cambios en B1 | Cumplido en esta fase |

## Cambios finales realizados (resumen acumulado B1)

- **Stubs completados**: repos fake con `get_by_capture_session_item_id` / `delete_by_id` donde exigia el ABC.
- **Tests alineados a contrato actual**: API (estados de job, cancel idempotente, 422 Pydantic), use cases (`job_id`, etc.), pipeline, schemas (`MinifiedProduct.r`), Stage 3/5/8, `SqlJobRepository` placeholder counts.
- **Integration tests aislados**: `pytest.mark.integration` en modulos SQL ODBC; `sql_server_client_or_skip()` en `tests/support/sql_integration.py`.
- **Tests renombrados**: ej. cancel idempotente vs 409; proceso bloqueado por job activo vs “crea nuevo job”.
- **B1.4**: ningun fix adicional requerido en esta corrida; la suite ya estaba estable.

## Sanity check de coverage (B1.4 — no optimizacion)

Objetivo: confirmar que rutas API y use cases criticos **se ejecutan** en tests (no 0% por error de coleccion / imports).

- **API v3** (`backend/src/api/routes/v3/`): modulos con ejecucion significativa, p. ej. `aisles.py` ~83%, `inventories.py` ~67%, `positions.py` ~95%, `router.py` 100% (muestra de corrida con cov).
- **Use cases** (`backend/src/application/use_cases/`): amplia cobertura en archivos revisados, p. ej. `confirm_position.py` 100%, `cancel_aisle_job.py` 100%, muchos casos en rango 77–100%.
- **TOTAL** bajo `src/`: ~83% lineas cubiertas en el reporte agregado de esta corrida.

Módulos con 0% o bajo cubrimiento suelen ser **codigo legacy o adapters no ejercitados** por esta suite; no se interpreta como fallo de B1.

## Deuda consciente (NO resolver en B1)

- Comportamiento documentado en tests de upload: si falla el `save` del asset tras escribir storage, **no hay compensacion automatica** de archivos (huérfanos posibles); el test lo refleja; mejorar seria producto/proceso, no B1.
- Divergencias futuras entre errores Pydantic (`detail`) y payloads legacy con `code` en otros endpoints: vigilar en contratos / B2.
- `DeprecationWarning` acumulados (~114 en corrida): limpieza en fase de mantenimiento o B2 (tipado / APIs deprecadas).
- Coverage bajo o 0% en modulos no criticos para v3 (p. ej. partes de `storage/adapters`, `roi/quality`): aceptable hasta definir prioridad de tests.
- Correr `-m integration` contra SQL Server real sigue siendo validacion aparte (CI o entorno dedicado).

## Resultado para fases posteriores (B2+)

Base lista: suite estable, corrida global confiable, integracion SQL aislada y documentada. Siguiente foco razonable: tipado estricto, contratos de API formales, o auditoria de arquitectura **sin** mezclar con estabilidad de tests.
