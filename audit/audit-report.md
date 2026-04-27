# Auditoría técnica inicial

Fecha:
Rama:
Commit:
Ejecutor:

## Objetivo

Documentar resultados de validaciones técnicas y de seguridad ejecutadas antes del deploy a `develop`, dejando evidencia trazable para análisis posterior.

## Alcance

Registrar hallazgos de backend, frontend y seguridad de sistema corriendo, sin corregirlos todavía en esta etapa.

## Herramientas previstas

- Backend: Ruff, Mypy, Bandit, pip-audit, Pytest, Trivy
- Frontend: ESLint, Typecheck, npm audit, Vitest
- Sistema corriendo: OWASP ZAP baseline scan

## Resumen de hallazgos

| Área | Herramienta | Severidad | Cantidad | Estado |
|---|---|---:|---:|---|
| Backend | - | - | - | Pendiente |
| Frontend | - | - | - | Pendiente |
| Seguridad | - | - | - | Pendiente |

## Resultados backend

| Herramienta | Reporte | Estado | Observaciones |
|---|---|---|---|
| Ruff | audit/raw/backend-ruff.txt | Pendiente | |
| Mypy | audit/raw/backend-mypy.txt | Pendiente | |
| Bandit | audit/raw/backend-bandit.json | Pendiente | |
| pip-audit | audit/raw/backend-pip-audit.json | Pendiente | |
| Pytest | audit/raw/backend-pytest.txt | Pendiente | |

## Resultados frontend

| Herramienta/Auditoría | Reporte | Estado | Observaciones |
|---|---|---|---|
| ESLint | audit/raw/frontend-eslint.txt | Pendiente | |
| Typecheck | audit/raw/frontend-typecheck.txt | Pendiente | |
| npm audit | audit/raw/frontend-npm-audit.json | Pendiente | |
| Vitest | audit/raw/frontend-vitest.txt | Pendiente | |
| useEffect audit | audit/raw/frontend-useeffects-audit.md | Pendiente | |
| Error handling audit | audit/raw/frontend-error-handling-audit.md | Pendiente | |
| Reusable components audit | audit/raw/frontend-reusable-components-audit.md | Pendiente | |

## Resultados arquitectura backend

| Auditoría | Reporte | Estado | Observaciones |
|---|---|---|---|
| Code smells | audit/raw/backend-code-smells.txt | Pendiente | |
| Complejidad | audit/raw/backend-complexity.txt | Pendiente | |
| Límites de imports | audit/raw/backend-import-boundaries.txt | Pendiente | |
| SOLID/GRASP | audit/raw/backend-solid-grasp-audit.md | Pendiente | |

## Resumen de hallazgos backend

| Herramienta | Severidad predominante | Cantidad aprox | Estado | Observaciones |
|---|---|---:|---|---|
| Ruff | Medio | 3545 | Detectado | Predominan problemas de estilo, tipado moderno e imports; hay un subconjunto con potencial impacto funcional. |
| Mypy | Alto | 80 (en 35 archivos) | Detectado | Errores de contratos de tipos, imports faltantes de stubs y retornos incompatibles en rutas/casos de uso. |
| Bandit | Medio | \~120+ | Detectado | Predominan LOW, con varios MEDIUM (especialmente patrones de SQL dinámico y subprocess). |
| pip-audit | Bajo | 0 vulnerabilidades conocidas | Detectado | Auditoría sin CVEs reportadas; el paquete local no publicado se marca como no auditable en PyPI. |
| Pytest | Crítico | 94 fallos (1785 tests) | Detectado | Alta tasa de fallos en áreas core de API v3, jobs, pipeline e integración de repositorios. |

### Hallazgos clave

- La suite backend ejecuta 1785 tests y reporta 94 fallos, concentrados en flujos operativos de pasillos, jobs y ejecución de pipeline.
- Hay un volumen alto de deuda de lint (3545), con mucha repetición en reglas de formato/imports y tipado legacy, lo que dificulta revisiones y estabilidad de cambios.
- Mypy reporta 80 errores en 35 archivos; destacan `import-not-found`, `arg-type`, `name-defined` y `return` en rutas v3 y servicios de aplicación.
- En Bandit aparecen patrones `B608` (construcción SQL por strings), con severidad MEDIUM, que requieren revisión manual para separar riesgos reales de consultas parametrizadas seguras.
- Se detectan patrones `try/except/pass` y `try/except/continue` en componentes de jobs/pipeline, que pueden ocultar fallos operativos.
- Hay alertas por uso de `subprocess` en servicios de arranque on-demand; aunque pueden ser controladas, requieren validación de entrada y contexto de ejecución.
- `pip-audit` no reporta CVEs conocidas en esta corrida, pero indica limitación para auditar el paquete local `dinamic-gemini` al no estar en PyPI.
- La cobertura global reportada por pytest-cov es 81%; existen módulos con cobertura baja/cero en zonas de almacenamiento y tracking que incrementan riesgo de regresión.

### Riesgos identificados

- **Riesgos técnicos**
  - Regresiones funcionales en rutas v3 y casos de uso críticos por el volumen de tests fallidos.
  - Mayor probabilidad de errores en runtime por inconsistencias de tipos no resueltas.
  - Menor mantenibilidad por exceso de findings repetitivos de lint.

- **Riesgos de seguridad**
  - Potenciales vectores de inyección SQL en puntos con query dinámica señalados por Bandit.
  - Manejo silencioso de excepciones que puede ocultar incidentes.
  - Superficie de riesgo asociada a ejecución de subprocess si no se valida estrictamente la entrada.

- **Riesgos de mantenibilidad**
  - Costo alto de onboarding y de revisión por ruido técnico acumulado.
  - Menor trazabilidad de fallos al coexistir deuda de estilo, tipado y pruebas en paralelo.
  - Dificultad para endurecer el Quality Gate sin una remediación incremental por lotes.

## Resumen de hallazgos frontend

| Herramienta/Auditoría | Severidad predominante | Cantidad aprox | Estado | Observaciones |
|---|---|---:|---|---|
| ESLint | Medio | 66 (40 errores, 26 warnings) | Detectado | En corrida actual sí ejecuta; en corridas previas quedó `SKIPPED` por ausencia de script `lint`. |
| Typecheck | - | 0 | OK | TypeScript compila sin errores en la corrida registrada. |
| npm audit | Medio | 7 moderadas | Detectado | Vulnerabilidades en cadena Vite/Vitest y paquetes transversales (`esbuild`, `postcss`, `yaml`). |
| Vitest | Alto | 19 archivos / 86 tests fallidos | Detectado | Fallos agrupados en suites principales de UI/flujo operacional. |
| useEffect audit | Medio | 46 usos / 20 archivos | Detectado | Conteos útiles, pero con posibles falsos positivos/negativos por heurística textual. |
| Error handling audit | Medio | 100 archivos con patrones | Detectado | Alta dispersión de patrones; requiere normalización por criticidad y UX. |
| Reusable components audit | Medio | 0 archivos candidatos / 300+ referencias UI | Detectado | Resultado inconsistente entre conteo de archivos y referencias; indica limitación del scanner. |

### Hallazgos clave frontend

- ESLint ya se ejecuta y reporta 66 findings (40 errores, 26 warnings), con foco en hooks React (`set-state-in-effect`, dependencias faltantes).
- Typecheck finaliza sin errores de TypeScript en la corrida auditada.
- `npm audit` reporta 7 vulnerabilidades moderadas (sin high/critical), principalmente en la cadena de build/test.
- Las remediaciones sugeridas por `npm audit` para Vite/Vitest implican upgrade semver major, por lo que requieren validación de compatibilidad.
- Vitest muestra 19 archivos de test fallidos y 86 tests fallidos, concentrados en `ExecutionLogPanel`, `CompareRunsPage`, `MetricsPage`, `InventoryDetailPage` y flujos de revisión.
- Se observa warning recurrente de entorno npm: `Unknown env config "devdir"`, que introduce ruido en reportes y puede afectar consistencia de ejecución.
- La auditoría de `useEffect` detecta uso extendido, pero los patrones avanzados (fetch/listeners/timers) aparecen en cero y pueden estar subdetectados.
- La auditoría de manejo de errores detecta alta cantidad de archivos con patrones (`onError`, `isError`, `try/catch`), lo que sugiere dispersión de estrategia.
- La auditoría de componentes reutilizables muestra un desalineamiento (0 archivos candidatos pero cientos de referencias), señal de que la heurística de descubrimiento necesita ajuste.

### Riesgos frontend identificados

- **Riesgos técnicos**
  - Fallos en suites de UI críticas pueden afectar flujos operativos y confianza en regresión.
  - Findings de hooks React pueden derivar en renders en cascada o efectos no controlados.
  - Cobertura de test efectiva reducida por volumen de suites inestables.

- **Riesgos de seguridad/dependencias**
  - Vulnerabilidades moderadas en dependencias de tooling (build/test) con posibilidad de impacto en entornos de desarrollo/CI.
  - Correcciones disponibles con upgrades mayores que pueden introducir incompatibilidades no triviales.

- **Riesgos de mantenibilidad**
  - Acumulación de findings de lint y fallos de test incrementa costo de cambios futuros.
  - Estrategia de manejo de errores potencialmente fragmentada entre páginas/hooks/componentes.
  - Detección incompleta de oportunidades de reutilización puede sostener duplicación de UI.

- **Riesgos de tooling**
  - Variabilidad entre corridas (por ejemplo lint `SKIPPED` en etapas previas) dificulta trazabilidad histórica si no se normaliza el entorno.
  - Warning `devdir` de npm ensucia reportes y complica lectura automatizada.

### Limitaciones de auditoría frontend

- ESLint no se ejecutó en corridas iniciales hasta agregar script `lint`; en la corrida actual ya ejecuta y reporta findings.
- Las auditorías estáticas por patrones de texto (`grep/find`) son aproximadas y no equivalen a análisis semántico AST.
- Sin `ripgrep`, el script usa fallback con `find/grep`; esto puede afectar precisión y performance.
- Resultados en cero (por ejemplo algunos patrones de `useEffect`) pueden ser falsos negativos por expresiones regulares o estructura del código.
- Parte de los fallos de tests puede estar influida por cambios de copy/i18n o contratos de texto, no solo por roturas de lógica de negocio.

## Observaciones generales

- Implementación progresiva del Quality Gate.
- En esta etapa se prioriza detección y documentación.
- La política de bloqueo se endurecerá en fases posteriores.
