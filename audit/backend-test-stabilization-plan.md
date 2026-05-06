# Plan de estabilización de tests backend — Preparación Fase B1

## Estado de la corrida pytest

- Comando detectado o recomendado:
  - `bash scripts/audit/run_backend_audit.sh`
  - Recomendación directa para B1: `cd backend && pytest -q`
- Confiabilidad de la corrida: **NO CONFIABLE** para analizar fallos funcionales.
- Evidencia principal:
  - `audit/raw/backend-pytest.txt` contiene:
    - `Pytest no instalado en el entorno actual.`
    - `timestamp: 2026-04-27 10:42:49`
- Total de tests: **No disponible** (corrida inválida).
- Fallidos: **No disponible** (corrida inválida).
- Errores: **No disponible** (corrida inválida).
- Skips: **No disponible** (corrida inválida).
- Warnings relevantes:
  - El entorno de ejecución no tenía `pytest` disponible, por lo que no existe señal confiable de regresiones backend en esta corrida.

## Clasificación por zona

| Zona | Carpeta de tests afectada | Carpeta productiva relacionada | Cantidad aprox de fallos | Severidad | Observaciones |
|---|---|---|---:|---|---|
| API | `backend/tests/api/` | `backend/src/api/routes/v3/` | N/D | Alta | Sin corrida válida, no se puede medir impacto real aún. |
| Application use-cases | `backend/tests/application/use_cases/` | `backend/src/application/use_cases/` | N/D | Alta | Sin evidencia ejecutable en `backend-pytest.txt`. |
| Pipeline | `backend/tests/infrastructure/pipeline/` | `backend/src/infrastructure/pipeline/`, `backend/src/pipeline/` | N/D | Alta | No hay traza de tests ejecutados para esta zona. |
| Fixtures / test setup | `backend/tests/conftest.py`, `backend/tests/fixtures/` | Helpers/factories de tests | N/D | Crítica | Bloquea todo el diagnóstico al no existir entorno pytest válido. |
| Otros | N/A | N/A | N/D | Media | No clasificable con evidencia actual. |

## Clasificación por causa probable

| Causa probable | Tests afectados | Motivo | Acción recomendada para B1 |
|---|---|---|---|
| ENTORNO_INVALIDO | Todo el scope backend | `pytest` no instalado en la corrida auditada, por lo tanto no hay resultados funcionales utilizables. | Preparar entorno reproducible (`backend` + dependencias dev) y re-ejecutar pytest completo antes de cualquier fix. |
| NECESITA_REVISION | API / Use-cases / Pipeline | Existen referencias históricas de fallos en documentos manuales, pero no están respaldadas por la evidencia raw actual. | Revalidar con corrida nueva y clasificar recién ahí por zona/causa técnica real. |
| FIXTURE_ROTA | Pendiente | No hay evidencia directa en la corrida actual, pero es categoría prioritaria por impacto transversal en múltiples tests. | Una vez corrida válida, priorizar errores de `conftest.py`/fixtures compartidas que bloqueen muchos casos. |
| MOCK_DESACTUALIZADO | Pendiente | Sin stack traces actuales no se puede confirmar, pero suele afectar API/use-cases al cambiar contratos internos. | En B1, revisar primero mocks que fallen en suites de endpoints core y casos de uso principales. |
| TEST_DESACTUALIZADO | Pendiente | Sin output de asserts no se puede distinguir entre test viejo y comportamiento correcto. | Clasificar solo tras obtener fallos reales en pytest y contrastar contratos actuales. |
| BUG_PRODUCTIVO_PROBABLE | Pendiente | Sin evidencia ejecutable no es posible afirmar bug real del backend. | Marcar únicamente cuando haya fallos repetibles con entorno válido y fixture/mock consistentes. |

## Orden recomendado para Fase B1

1. API tests
2. Application use-cases
3. Pipeline tests
4. Fixtures/helpers compartidos, solo si bloquean muchos tests

## Tests prioritarios para atacar primero

En esta fase no se listan tests específicos porque la corrida actual es inválida. Para iniciar B1 con control:

- Priorizar primero archivos bajo `backend/tests/api/` que cubran endpoints v3 core.
- Luego abordar `backend/tests/application/use_cases/` para contratos de orquestación.
- Continuar con `backend/tests/infrastructure/pipeline/` por impacto operativo.
- Si aparece falla transversal de setup, atender `backend/tests/conftest.py` y `backend/tests/fixtures/` antes de seguir.

## Qué NO corregir todavía

- No corregir mypy.
- No corregir ruff.
- No corregir bandit.
- No corregir arquitectura.
- No corregir complejidad.
- No hacer refactors globales.

## Criterio de cierre de Fase B0

La fase B0 queda cerrada cuando:

- Existe un mapa claro de fallos de pytest o, en su defecto, una confirmación explícita de que la corrida fue inválida.
- Los fallos (o ausencia de evidencia válida) están agrupados por zona.
- Los fallos (o hipótesis) tienen causa probable documentada.
- Hay un orden concreto para ejecutar B1.
- No se modificó código productivo.
- No se corrigieron tests todavía.
