# Backlog de bugs y vulnerabilidades

## Críticos

### AUD-001 - Fallos masivos en pruebas de flujo operativo de pasillos y jobs
- Área: Backend
- Herramienta: Pytest
- Severidad: Crítico
- Archivo/Ruta: `backend/tests/api/test_aisles_v3_wiring.py`, `backend/tests/application/use_cases/test_aisle_processing.py`, `backend/tests/infrastructure/pipeline/`
- Descripción: Se observan múltiples fallos en flujos core de creación/cancelación/procesamiento de jobs de pasillo y coordinación de pipeline.
- Riesgo: Alta probabilidad de regresiones en operaciones principales y resultados inconsistentes en producción.
- Evidencia: `audit/raw/backend-pytest.txt` (94 fallos totales; resumen final y short test summary).
- Recomendación futura: Priorizar corrección por dominios (API v3 -> use cases -> infraestructura) y validar con smoke tests de negocio.
- Estado: Pendiente

### AUD-002 - Inestabilidad en casos de uso de carga y gestión de assets de pasillo
- Área: Backend
- Herramienta: Pytest
- Severidad: Crítico
- Archivo/Ruta: `backend/tests/application/use_cases/test_upload_aisle_assets.py`, `backend/tests/application/use_cases/test_delete_aisle_source_asset.py`
- Descripción: Fallan múltiples escenarios de upload/listado/borrado y rollback de assets.
- Riesgo: Riesgo directo sobre disponibilidad e integridad del flujo de carga de evidencias.
- Evidencia: `audit/raw/backend-pytest.txt`
- Recomendación futura: Corregir contratos transaccionales y reglas de estado antes de endurecer el gate.
- Estado: Pendiente

## Altos

### AUD-003 - Errores de tipado en rutas v3 con retornos y dependencias no resueltas
- Área: Backend
- Herramienta: Mypy
- Severidad: Alto
- Archivo/Ruta: `backend/src/api/routes/v3/aisles.py`, `backend/src/api/routes/v3/assets.py`, `backend/src/api/routes/v3/inventories.py`, `backend/src/api/routes/v3/capture_sessions.py`
- Descripción: Se detectan `Missing return statement`, `name-defined` y firmas incompatibles en rutas HTTP.
- Riesgo: Posible comportamiento no determinista en handlers y degradación de contratos de API.
- Evidencia: `audit/raw/backend-mypy.txt`
- Recomendación futura: Normalizar firmas/retornos y asegurar imports/símbolos explícitos por ruta.
- Estado: Pendiente

### AUD-004 - Errores de tipado en integración de pipeline y adapters LLM
- Área: Backend
- Herramienta: Mypy
- Severidad: Alto
- Archivo/Ruta: `backend/src/pipeline/hybrid_inventory_pipeline.py`, `backend/src/llm/openai_sdk_adapter.py`, `backend/src/llm/anthropic_sdk_adapter.py`
- Descripción: Se observan incompatibilidades de tipos en invocaciones y payloads complejos.
- Riesgo: Fallos en tiempo de ejecución en rutas de procesamiento y análisis.
- Evidencia: `audit/raw/backend-mypy.txt`
- Recomendación futura: Ajustar contratos tipados de adapters y DTOs intermedios.
- Estado: Pendiente

### AUD-005 - Dependencias sin stubs tipados en rutas críticas
- Área: Backend
- Herramienta: Mypy
- Severidad: Alto
- Archivo/Ruta: `backend/src/env_settings/sqlserver_resolution.py`, `backend/src/database/sqlserver.py`, `backend/src/infrastructure/repositories/*`, `backend/src/auth/security.py`
- Descripción: `import-not-found` / `import-untyped` para `pyodbc`, `boto3`, `passlib`.
- Riesgo: Pérdida de cobertura de análisis estático en componentes de persistencia y autenticación.
- Evidencia: `audit/raw/backend-mypy.txt`
- Recomendación futura: Incorporar stubs o exclusiones tipadas justificadas por módulo.
- Estado: Pendiente

### AUD-006 - Posibles vectores de SQL injection por construcción dinámica de queries
- Área: Backend
- Herramienta: Bandit
- Severidad: Alto
- Archivo/Ruta: `backend/src/infrastructure/repositories/sql_job_repository.py`, `sql_product_record_repository.py`, `sql_raw_label_repository.py`, `sql_source_asset_repository.py`, `sql_normalized_label_repository.py`
- Descripción: Hallazgos `B608` de severidad MEDIA por uso de f-strings/placeholders dinámicos en SQL.
- Riesgo: Si algún valor no está controlado/parametrizado, podría abrir vector de inyección.
- Evidencia: `audit/raw/backend-bandit.json`
- Recomendación futura: Revisar consulta por consulta y documentar casos seguros con parametrización estricta.
- Estado: Pendiente

## Medios

### AUD-007 - Deuda de lint elevada y repetitiva en backend
- Área: Backend
- Herramienta: Ruff
- Severidad: Medio
- Archivo/Ruta: `backend/` (global)
- Descripción: Se reportan 3545 errores, con fuerte repetición de reglas de formato/imports/tipado moderno.
- Riesgo: Alto ruido técnico que dificulta detectar problemas realmente críticos en revisiones.
- Evidencia: `audit/raw/backend-ruff.txt` (línea final: `Found 3545 errors.`)
- Recomendación futura: Plan de remediación por lotes (primero imports/whitespace, luego upgrades de typing).
- Estado: Pendiente

### AUD-008 - Manejo silencioso de excepciones en jobs y pipeline
- Área: Backend
- Herramienta: Bandit
- Severidad: Medio
- Archivo/Ruta: `backend/src/jobs/dev_reset_local_jobs.py`, `backend/src/jobs/worker.py`, `backend/src/pipeline/hybrid_inventory_pipeline.py`
- Descripción: Hallazgos `B110`/`B112` por `except ...: pass/continue`.
- Riesgo: Ocultamiento de errores operativos y pérdida de trazabilidad de incidentes.
- Evidencia: `audit/raw/backend-bandit.json`
- Recomendación futura: Registrar excepciones y aplicar manejo explícito por tipo de error.
- Estado: Pendiente

### AUD-009 - Uso de subprocess con validación pendiente de inputs
- Área: Backend
- Herramienta: Bandit
- Severidad: Medio
- Archivo/Ruta: `backend/src/infrastructure/services/on_demand_worker_launch_service.py`
- Descripción: Hallazgos `B404`/`B603` por uso de `subprocess` en lanzamiento de procesos.
- Riesgo: Riesgo de ejecución no deseada si se amplía superficie de entrada no confiable.
- Evidencia: `audit/raw/backend-bandit.json`
- Recomendación futura: Endurecer validación/origen del comando y auditar contexto de ejecución.
- Estado: Pendiente

### AUD-010 - Errores de tipos en consolidación y normalización de datos
- Área: Backend
- Herramienta: Mypy
- Severidad: Medio
- Archivo/Ruta: `backend/src/consolidate/consolidate.py`, `backend/src/application/mappers/position_canonical_view.py`, `backend/src/jobs/job_store.py`
- Descripción: Operaciones con tipos opcionales o mixtos (`str | None`, `dict` tipado débil) generan incompatibilidades.
- Riesgo: Cálculos/serializaciones inconsistentes en escenarios borde.
- Evidencia: `audit/raw/backend-mypy.txt`
- Recomendación futura: Tipado explícito de estructuras intermedias y validación previa a operaciones aritméticas.
- Estado: Pendiente

## Bajos

### AUD-011 - Hallazgos de estilo de baja criticidad (whitespace/import ordering)
- Área: Backend
- Herramienta: Ruff
- Severidad: Bajo
- Archivo/Ruta: `backend/tests/`, `backend/scripts/`
- Descripción: Reglas como `W293`, `I001`, `W292` aparecen en múltiples archivos y no implican fallo funcional directo.
- Riesgo: Bajo impacto funcional; sí afecta consistencia del código y revisabilidad.
- Evidencia: `audit/raw/backend-ruff.txt`
- Recomendación futura: Aplicar autofix controlado por carpetas y validar en CI.
- Estado: Pendiente

### AUD-012 - Hallazgos de pseudoaleatoriedad y asserts en contexto no criptográfico
- Área: Backend
- Herramienta: Bandit
- Severidad: Bajo
- Archivo/Ruta: `backend/src/llm/anthropic_sdk_adapter.py`, `backend/src/llm/costing.py`, `backend/src/pipeline/services/multi_provider_analysis_execution.py`
- Descripción: Alertas `B311` y `B101` por `random` y `assert`; en principio no están en contexto criptográfico o de control de acceso.
- Riesgo: Bajo en contexto actual, pero requiere confirmación técnica para evitar falsos supuestos.
- Evidencia: `audit/raw/backend-bandit.json`
- Recomendación futura: Documentar justificación técnica o reemplazar patrones donde corresponda.
- Estado: Pendiente

## Falsos positivos

- **Bandit B608 en repositorios SQL con parámetros controlados**: parte de los hallazgos puede corresponder a SQL dinámico con placeholders seguros y parámetros separados.
- **Bandit B101 en asserts de validación interna**: algunos casos pueden ser validaciones internas no expuestas a entrada externa.
- **Bandit B404/B603 en subprocess de worker on-demand**: posible falso positivo parcial si la fuente de comandos está completamente controlada por configuración interna.
- **Mypy import-not-found de librerías sin stubs oficiales**: en varios casos no implica bug runtime, sino cobertura tipada incompleta.

## Observaciones generales

- El backend está funcionalmente activo, pero presenta una deuda técnica significativa en calidad estática (lint + typing) y estabilidad de pruebas.
- La prioridad para la siguiente fase de remediación debería enfocarse en: (1) pruebas fallidas core, (2) hallazgos de seguridad MEDIUM, (3) contratos de tipos en rutas y pipeline.
- El material generado en `audit/raw/` es suficiente para construir un plan de corrección por lotes sin alterar aún el comportamiento de deploy.
