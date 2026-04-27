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
