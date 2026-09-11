# Validación: worker SQL repository fix

## Comandos ejecutados

```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/jobs/test_worker_db_claim.py \
  backend/tests/jobs/test_worker_runtime.py \
  backend/tests/api/test_health_ready_repository_backend_phase2.py \
  backend/tests/api/test_schema_guard_readiness.py \
  backend/tests/jobs/test_run_worker_entrypoint.py \
  --override-ini='addopts='

cd backend && .venv/bin/ruff check \
  src/jobs/job_store.py src/jobs/worker.py src/jobs/worker_runtime.py \
  src/jobs/run_worker.py src/api/server.py \
  tests/jobs/test_worker_db_claim.py tests/jobs/test_worker_runtime.py \
  tests/api/test_health_ready_repository_backend_phase2.py

cd backend && .venv/bin/mypy \
  src/jobs/job_store.py src/jobs/worker.py src/jobs/worker_runtime.py \
  src/jobs/run_worker.py src/api/server.py
```

## Resultados

| Comando | Resultado |
|---------|-----------|
| pytest (módulos listados) | **33 passed** |
| ruff check (archivos tocados) | **All checks passed** |
| mypy (módulos src tocados) | **Success: no issues found in 5 source files** |

No se ejecutó el quality gate completo (`pytest` de todo el backend, frontend, security). No se ejecutaron migraciones ni se tocó DEV/producción.

## Pruebas agregadas o actualizadas

### `backend/tests/jobs/test_worker_db_claim.py`

- Idle v3 + `_db_repos() is None` + SQL on: **no** ERROR (regresión del spam).
- SQL on + repo v3 sin `claim_next_queued_job` + legacy None: `repositories_not_initialized`, log una sola vez en dos polls.
- SQL on + `get_job_repo` lanza: `v3_job_repository_unavailable`, log una vez.
- Recuperación: ERROR luego `job_worker_recovered`.
- Tests previos de claim v3, claim legacy, fallback memoria, exception de claim DB, `worker_loop`: preservados.

### `backend/tests/jobs/test_worker_runtime.py`

- Rate limit de logs.
- Recuperación con downtime.
- `/ready` problem cuando required y no started.
- Thread muerto → `worker_terminated`.
- Stop/join del loop.
- Instancias aisladas de runtime.

### `backend/tests/api/test_health_ready_repository_backend_phase2.py`

- 503 `JOB_WORKER_UNAVAILABLE` / `detail=repositories_not_initialized`.
- Tras `mark_cycle_ok` con thread vivo: `/ready` 200 `{"ok": true}`.
- Tests existentes de schema/backend: el fixture pone worker **no required** para no mezclar contratos.

## Casos cubiertos vs pedido

| Pedido | Cobertura |
|--------|-----------|
| SQL + worker + repos presentes: inicia, claim, ready OK | Unit: v3 claim + idle no degrada ready; loop usa `claim_next_job` |
| SQL + worker + repos ausentes: no ready, código, no loop silencioso | 503 + log once |
| SQL off / memoria | `test_claim_next_job_legacy_fallback_when_db_disabled` |
| Falla de init, excepción original | `error_type` en snapshot; traceback solo en la primera transición |
| Worker termina inesperado | `worker_terminated` → readiness |
| Recuperación + log | `job_worker_recovered` |
| Log no por cada poll | count == 1 en dos claims |
| No dos workers / shutdown | guard `is_thread_alive`; `request_stop` + `join` |
| `test_worker_db_claim.py` | intención preservada; contrato de ERROR actualizado |

## Evidencia `/ready`

Cuando el worker embebido es obligatorio y el claim path está `repositories_not_initialized`:

```json
{"ok": false, "reason": "JOB_WORKER_UNAVAILABLE", "detail": "repositories_not_initialized"}
```

HTTP 503. `/health` sigue `ok: true` (liveness).

Cola vacía con v3 claimable: no se marca unavailable → `/ready` 200.

## Evidencia de claim con repositorios

`test_claim_next_job_prefers_v3_inventory_jobs_claim` y `test_claim_next_job_prefers_db_claim` siguen pasando: con repo v3 o legacy fake se reclama un job y se mapea a `JobRecord`.

## Limitaciones

- No se re-ejecutó el contenedor OpenCloud DEV; el spam en ese host solo se infiere del código + tests.
- No hay test de integración ODBC real de claim en esta corrida (haría falta SQL Server de test).
- `on_event` de FastAPI sigue deprecado (preexistente); no se migró a lifespan.

## Status final

`IMPLEMENTED_WITH_LIMITATIONS`
