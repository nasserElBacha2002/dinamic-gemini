# Phase 3 — Test report (lease fencing)

## Archivos

| Archivo | Tipo | Cobertura esperada |
|---|---|---|
| `backend/tests/domain/jobs/test_job_lease.py` | Unit domain | `JobLease` frozen fields; `LeaseRenewalResult.renewed`; enum stability; `LeaseWriteResult.applied`; `JobLeaseLostError` context/defaults |
| `backend/tests/infrastructure/repositories/test_memory_job_lease_fencing.py` | Unit/integration memory | Claim token=1; renew OK (token estable); renew wrong owner → LOST; renew after expiry → EXPIRED; reacquire increments token; reacquire not expired → CONFLICT; stale merge rejected; current owner merge OK; sequential steal chain; heartbeat delegates renew; complete/fail stale reject; assert vs finalization race |
| `backend/tests/infrastructure/pipeline/test_v3_job_monitoring_lease_lost.py` | Unit worker | Heartbeat lease lost → `runtime_abort_event`; **no** `fail_job_and_aisle` |
| `backend/tests/integration/jobs/test_sql_job_lease_fencing.py` | SQL IT | Monotonic token; stale heartbeat/result/finalization rejected; dual-connection steal (1 ACQUIRED / 1 CONFLICT) |
| `backend/tests/infrastructure/repositories/test_sql_job_repository.py` | SQL unit (extendido) | Claim/lease SQL params y persistencia de columnas donde se aserte en suite existente |

## Matriz de cobertura

| Área | Memory | Monitoring | SQL IT |
|---|---|---|---|
| Domain VOs / error | ✓ domain tests | — | — |
| Acquire + token | ✓ | — | ✓ |
| Renew CAS | ✓ | ✓ (via mock renew LOST) | ✓ stale renew |
| Steal / reacquire | ✓ | — | ✓ incl. dual thread |
| Stale result merge | ✓ | — | ✓ |
| complete/fail if leased | ✓ | — | ✓ complete |
| Abort without FAIL | — | ✓ | — |
| Cancel / artifacts / promotion fenced | ✗ (gap) | ✗ | ✗ |

## Cómo correr

```bash
cd backend
.venv/bin/python -m pytest \
  tests/domain/jobs/test_job_lease.py \
  tests/infrastructure/repositories/test_memory_job_lease_fencing.py \
  tests/infrastructure/pipeline/test_v3_job_monitoring_lease_lost.py \
  -q --no-cov

# SQL Server + migration 0072 required (else skip):
.venv/bin/python -m pytest \
  tests/integration/jobs/test_sql_job_lease_fencing.py \
  -q --no-cov
```

## Criterio de evidencia

- **Local sin SQL:** domain + memory + monitoring deben PASS; SQL IT SKIPPED no implica contrato SQL validado.
- **Merge SQL environments:** SQL IT PASS obligatorio tras 0072.
- No se reclama cobertura Prometheus (no existe).
- No se reclama Phase 4.
