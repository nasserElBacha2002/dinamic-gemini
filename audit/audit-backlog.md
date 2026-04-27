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

### AUD-013 - Hallazgos ESLint en hooks React con riesgo de renders en cascada
- Área: Frontend
- Herramienta: ESLint
- Severidad: Alto
- Archivo/Ruta: `frontend/src/components/CreateAisleDialog.tsx`, `frontend/src/components/ExecutionLogPanel.tsx`, `frontend/src/components/ui/ImageViewer.tsx`, `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx`
- Descripción: Se detectan errores `react-hooks/set-state-in-effect` y dependencias incompletas en hooks.
- Riesgo: Posibles rerenders innecesarios, efectos no deterministas y comportamiento UI difícil de estabilizar.
- Evidencia: `audit/raw/frontend-eslint.txt`
- Recomendación futura: Revisar patrones de efectos y mover inicializaciones/derivaciones a `useMemo`/estado derivado cuando corresponda.
- Estado: Pendiente

### AUD-014 - Deuda de lint frontend concentrada en reglas de hooks y refresh
- Área: Frontend
- Herramienta: ESLint
- Severidad: Medio
- Archivo/Ruta: `frontend/src/` (global)
- Descripción: La corrida reporta 66 findings (40 errores, 26 warnings), incluyendo `react-refresh/only-export-components` y warnings de dependencias.
- Riesgo: Ruido técnico elevado que dificulta priorizar fallos funcionales en PRs.
- Evidencia: `audit/raw/frontend-eslint.txt`
- Recomendación futura: Aplicar remediación por lotes de reglas, empezando por errores bloqueantes de hooks.
- Estado: Pendiente

### AUD-015 - Drift de tooling de lint entre corridas (SKIPPED previo vs ejecución actual)
- Área: Frontend
- Herramienta: ESLint
- Severidad: Medio
- Archivo/Ruta: `frontend/package.json`, `scripts/audit/run_frontend_audit.sh`
- Descripción: En fases previas lint quedó `SKIPPED` por falta de script; actualmente ejecuta, lo que evidencia inconsistencia histórica de setup.
- Riesgo: Trazabilidad incompleta de calidad frontend entre ejecuciones del gate.
- Evidencia: historial de `audit/raw/frontend-eslint.txt` + reportes de Fase 3.
- Recomendación futura: Mantener control de precondiciones del entorno y versionar checklist de tooling mínimo.
- Estado: Pendiente

### AUD-016 - Vulnerabilidades moderadas en cadena de build/test frontend
- Área: Frontend
- Herramienta: npm audit
- Severidad: Alto
- Archivo/Ruta: `frontend/package-lock.json`
- Descripción: Se reportan 7 vulnerabilidades moderadas en `vite`, `vitest`, `vite-node`, `@vitest/mocker`, `esbuild`, `postcss`, `yaml`.
- Riesgo: Riesgo de seguridad en toolchain de desarrollo/CI y posibles superficies de ataque indirectas.
- Evidencia: `audit/raw/frontend-npm-audit.json`
- Recomendación futura: Planificar remediación por dependencias, priorizando advisories con CVE/CWE de mayor impacto.
- Estado: Pendiente

### AUD-017 - Remediaciones de npm audit requieren upgrades major (riesgo de compatibilidad)
- Área: Frontend
- Herramienta: npm audit
- Severidad: Medio
- Archivo/Ruta: `frontend/package.json`, `frontend/package-lock.json`
- Descripción: Las correcciones propuestas para `vite`/`vitest` apuntan a versiones semver major.
- Riesgo: Posibles cambios breaking en tooling, tests y configuración de build.
- Evidencia: `audit/raw/frontend-npm-audit.json`
- Recomendación futura: Ejecutar upgrade controlado en rama dedicada con matriz de tests y smoke de build.
- Estado: Pendiente

### AUD-018 - Fallos de tests en ExecutionLogPanel afectan observabilidad operativa
- Área: Frontend
- Herramienta: Vitest
- Severidad: Alto
- Archivo/Ruta: `frontend/tests/ExecutionLogPanel.test.tsx`
- Descripción: 6 de 8 tests fallan en la suite, incluyendo validaciones de rendering y contenido.
- Riesgo: Menor confiabilidad en UI de trazabilidad/observabilidad de ejecución.
- Evidencia: `audit/raw/frontend-vitest.txt`
- Recomendación futura: Reconciliar contratos de texto/datos de panel con expectativas de test.
- Estado: Pendiente

### AUD-019 - Fallos en CompareRunsPage impactan flujos comparativos de analítica
- Área: Frontend
- Herramienta: Vitest
- Severidad: Alto
- Archivo/Ruta: `frontend/tests/CompareRunsPage.test.tsx`, `frontend/tests/CompareRunsDialog.test.tsx`
- Descripción: Fallos repetidos en pruebas de comparación entre corridas y su diálogo asociado.
- Riesgo: Riesgo funcional en vistas de benchmarking y análisis comparativo para usuarios.
- Evidencia: `audit/raw/frontend-vitest.txt`
- Recomendación futura: Validar contratos de filtros, copys y dependencias de datos en vistas de comparación.
- Estado: Pendiente

### AUD-020 - Fallos en MetricsPage y dashboards asociados
- Área: Frontend
- Herramienta: Vitest
- Severidad: Alto
- Archivo/Ruta: `frontend/tests/MetricsPage.test.tsx`
- Descripción: 7 de 13 tests fallan en la suite de métricas.
- Riesgo: Posible degradación en tablero de métricas y confianza de indicadores mostrados.
- Evidencia: `audit/raw/frontend-vitest.txt`
- Recomendación futura: Ajustar fixtures/expectativas de métricas y validar adaptadores de datos de analytics.
- Estado: Pendiente

### AUD-021 - Inestabilidad amplia de pruebas frontend en suites core
- Área: Frontend
- Herramienta: Vitest
- Severidad: Crítico
- Archivo/Ruta: `frontend/tests/` (global, 19 archivos fallidos)
- Descripción: La corrida registra 19 archivos fallidos y 86 tests fallidos sobre 426.
- Riesgo: Alto riesgo de regresiones al no contar con red de seguridad confiable para cambios de UI/estado.
- Evidencia: `audit/raw/frontend-vitest.txt` (resumen final)
- Recomendación futura: Plan de estabilización por dominios (auth, inventario, revisión, analytics) con gate incremental.
- Estado: Pendiente

### AUD-022 - Limitaciones del scanner de useEffect para patrones avanzados
- Área: Frontend
- Herramienta: useEffect audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/` (múltiples archivos)
- Descripción: Se detectan 46 usos de `useEffect`, pero varios patrones avanzados figuran en cero, sugiriendo subdetección por heurística.
- Riesgo: Falsos negativos en detección de side-effects problemáticos o lógica de API dentro de efectos.
- Evidencia: `audit/raw/frontend-useeffects-audit.md`
- Recomendación futura: Mejorar scanner (AST o regex multiline robusta) y cruzar con findings de ESLint hooks.
- Estado: Pendiente

### AUD-023 - Riesgo de interpretación parcial en auditoría de manejo de errores
- Área: Frontend
- Herramienta: Error handling audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/`, `frontend/tests/`
- Descripción: El reporte marca 100 archivos con patrones de error, pero no diferencia criticidad ni contexto (UI, test, utilidades).
- Riesgo: Backlog sobredimensionado sin priorización clara; posible mezcla de ruido y deuda real.
- Evidencia: `audit/raw/frontend-error-handling-audit.md`
- Recomendación futura: Clasificar por capas (runtime UI vs test helpers) y por impacto de usuario.
- Estado: Pendiente

### AUD-024 - Inconsistencia en auditoría de componentes reutilizables
- Área: Frontend
- Herramienta: Reusable components audit
- Severidad: Medio
- Archivo/Ruta: `frontend/src/components`, `frontend/src/pages`, `frontend/src/features`
- Descripción: Reporta 0 archivos candidatos, pero cientos de referencias a componentes base (`Button`, `Table`, `Dialog`, etc.).
- Riesgo: Falso negativo en detección de duplicación y oportunidades de abstracción.
- Evidencia: `audit/raw/frontend-reusable-components-audit.md`
- Recomendación futura: Ajustar descubrimiento de archivos por rutas y mejorar criterio de agrupación por patrón.
- Estado: Pendiente

### AUD-025 - Warning recurrente de npm por configuración de entorno (devdir)
- Área: Frontend
- Herramienta: npm / tooling
- Severidad: Bajo
- Archivo/Ruta: entorno npm local (visible al inicio de reportes)
- Descripción: Se repite `npm warn Unknown env config "devdir"` en lint, typecheck, audit y tests.
- Riesgo: Ruido operativo y potencial confusión en pipelines/entornos compartidos.
- Evidencia: `audit/raw/frontend-eslint.txt`, `audit/raw/frontend-typecheck.txt`, `audit/raw/frontend-npm-audit.json`, `audit/raw/frontend-vitest.txt`
- Recomendación futura: Auditar configuración npm del entorno y documentar estándar para ejecución local/CI.
- Estado: Pendiente

### AUD-026 - Warnings de React Router future flags en ejecución de tests
- Área: Frontend
- Herramienta: Vitest
- Severidad: Bajo
- Archivo/Ruta: suites de UI con enrutamiento (`frontend/tests/...`)
- Descripción: Se observan warnings de future flags de React Router durante tests.
- Riesgo: Riesgo de deuda de compatibilidad para próximas versiones del router.
- Evidencia: `audit/raw/frontend-vitest.txt`
- Recomendación futura: Planificar adopción progresiva de future flags y actualizar setup de test/router wrappers.
- Estado: Pendiente

## Falsos positivos

- **Bandit B608 en repositorios SQL con parámetros controlados**: parte de los hallazgos puede corresponder a SQL dinámico con placeholders seguros y parámetros separados.
- **Bandit B101 en asserts de validación interna**: algunos casos pueden ser validaciones internas no expuestas a entrada externa.
- **Bandit B404/B603 en subprocess de worker on-demand**: posible falso positivo parcial si la fuente de comandos está completamente controlada por configuración interna.
- **Mypy import-not-found de librerías sin stubs oficiales**: en varios casos no implica bug runtime, sino cobertura tipada incompleta.
- **useEffect audit con patrones en cero**: algunos conteos pueden ser falsos negativos por limitaciones de regex/fallback textual.
- **Reusable components audit (0 archivos vs alta referencia)**: resultado potencialmente sesgado por heurística de descubrimiento de archivos.

## Observaciones generales

- El backend está funcionalmente activo, pero presenta una deuda técnica significativa en calidad estática (lint + typing) y estabilidad de pruebas.
- La prioridad para la siguiente fase de remediación debería enfocarse en: (1) pruebas fallidas core, (2) hallazgos de seguridad MEDIUM, (3) contratos de tipos en rutas y pipeline.
- El material generado en `audit/raw/` es suficiente para construir un plan de corrección por lotes sin alterar aún el comportamiento de deploy.
- En frontend, la mayor deuda actual se concentra en estabilidad de tests, findings de hooks en ESLint y vulnerabilidades moderadas de toolchain.
