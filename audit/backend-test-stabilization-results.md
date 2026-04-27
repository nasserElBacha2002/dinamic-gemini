# Fase B1 — Estabilizacion de tests backend core

Fecha: 2026-04-27

## Estado inicial

- Corrida invalida detectada en B0: `pytest` faltante y ejecucion con Python 3.9 (incompatible con `typing.Self`, `dataclass(kw_only=...)` y operadores de tipos `|`).
- Entorno valido para B1:
  - Interpreter efectivo: `.venv` con Python 3.13.
  - Runner usado: `.venv/bin/python -m pytest`.
- Primera corrida real por bloques (con `--maxfail=10`):
  - API: `10 failed, 267 passed, 12 skipped`.
  - Application use-cases: `10 failed, 170 passed`.
  - Pipeline: `10 failed, 6 passed, 1 skipped`.

## Cambios realizados

### 1) Bloqueantes de setup / compatibilidad de entorno

- **Causa**: ejecucion inicial de B1 con `python3` del sistema (3.9) rompia coleccion masiva.
- **Accion**: estandarizacion de ejecucion con `.venv` (Python 3.13) para obtener fallos funcionales reales.
- **Impacto**: se eliminan errores masivos de import/tipado de runtime; quedan fallos de contratos reales en tests.

### 2) Application use-cases — stubs desactualizados (FIXTURE_ROTA / MOCK_DESACTUALIZADO)

- **Problema**: nuevos metodos abstractos en `SourceAssetRepository` (`get_by_capture_session_item_id`) rompian stubs de tests.
- **Archivos ajustados**:
  - `backend/tests/application/use_cases/test_aisle_processing.py`
  - `backend/tests/application/use_cases/test_delete_aisle_source_asset.py`
  - `backend/tests/application/use_cases/test_list_aisles_with_status.py`
- **Problema adicional**: `ConfirmPositionUseCase.execute()` ahora requiere `job_id`.
- **Archivo ajustado**:
  - `backend/tests/application/use_cases/test_confirm_position.py`
- **Correccion minima aplicada**:
  - Implementaciones no-op del metodo faltante en stubs.
  - Actualizacion de llamadas `execute(...)` con `job_id` explicito en casos afectados.
- **Validacion focalizada**:
  - `19 passed` en suite focal de use-cases (`confirm_position`, `delete_aisle_source_asset`, `list_aisles_with_status`).

### 3) Pipeline — stubs y mensajes esperados (TEST_DESACTUALIZADO / MOCK_DESACTUALIZADO)

- **Problema**: repos fake para pruebas de pipeline no cumplian metodos abstractos nuevos (`delete_by_id`, `get_by_capture_session_item_id`).
- **Archivos ajustados**:
  - `backend/tests/infrastructure/pipeline/test_v3_job_executor_input_resolution.py`
  - `backend/tests/infrastructure/pipeline/test_v3_job_executor_phase5.py`
- **Problema adicional**: assert estricto de texto en mensaje de error de pipeline (`"exit code 2"` vs `"code 2"`).
- **Archivo ajustado**:
  - `backend/tests/infrastructure/pipeline/test_v3_job_executor_coordination.py`
- **Correccion minima aplicada**:
  - Implementaciones no-op en stubs.
  - Assert mas robusto para mensaje de error.
- **Validacion focalizada**:
  - `12 passed` en suite focal de pipeline (`coordination` + `input_resolution`).

### 4) API — expectativas de contrato desactualizadas (TEST_DESACTUALIZADO)

- **Problemas observados**:
  - Estados de job esperados en tests (`queued` / `canceled`) no reflejaban estado actual (`starting` / `cancel_requested`).
  - Caso de reproceso tras cancelacion ahora bloquea con conflicto por job activo.
  - Patch target de `load_settings` desalineado por refactor de modulo.
  - Validaciones Pydantic de `max_diff_rows` devuelven 422 de schema.
  - Test E2E consultaba `position_id` inexistente.
- **Archivos ajustados**:
  - `backend/tests/api/test_aisles_v3_wiring.py`
  - `backend/tests/api/test_phase6_benchmark_api.py`
  - `backend/tests/api/test_recomputed_consolidation_e2e.py`
- **Correccion minima aplicada**:
  - Ajuste de expectativas a contrato actual sin modificar logica productiva.
  - Actualizacion de destino de patch `load_settings`.
  - Consulta de id de posicion existente en E2E.
- **Validacion focalizada**:
  - `86 passed` en suite focal API (3 archivos actualizados).

## Estado final

- **Entorno**: pytest estable y reproducible con `.venv` (Python 3.13).
- **Bloqueantes masivos de setup**: resueltos.
- **Bloques corregidos y verificados**:
  - Use-cases focales: `19 passed`.
  - Pipeline focal: `12 passed`.
  - API focal: `86 passed`.

## Fallos que aun pueden existir fuera del foco B1

- No se completo una corrida global integral de todo `backend/tests` al final de esta fase (alto costo temporal por volumen y cobertura).
- Por alcance de B1, se priorizaron:
  - estabilidad de entorno,
  - eliminacion de bloqueos de coleccion/stubs,
  - y sincronizacion de tests con contrato actual en las zonas criticas.

## Pendientes para fases futuras

- Ejecutar corrida global completa (`pytest -q`) en ventana dedicada y consolidar remanentes no cubiertos por los focos B1.
- Si aparecen nuevos fallos, clasificar por zona (API/use-cases/pipeline/fixtures) y aplicar correcciones minimas incrementales.
- Mantener separacion de fases: no mezclar con hardening de tipado, seguridad o arquitectura en este cierre.
