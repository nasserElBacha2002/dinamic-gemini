# Phase 6 — Refactor candidate matrix

Phase 5 status: `CORRECTIONS_APPLIED` (residual PLANNED metrics non-blocking). Phase 6 proceeds.

| Componente | Problema | Riesgo | Prioridad | Acción | Estado |
| ---------- | -------- | ------ | --------- | ------ | ------ |
| `JobResultUnitOfWork` / `persist_aisle_result` | `getattr(uow, "fence_job_lease")` — Protocol gap | P0 fencing | P0 | Add `fence_job_lease` → bool to Protocol; Memory + SQL; Persist fallback only when False | DONE |
| `observability_download_gate` | FastAPI `HTTPException` in application | P0 layer | P0 | Domain exception; map in API | DONE |
| `RecoverStaleJobUseCase` / launch | String-match + getattr on exceptions | P0 recovery | P0 | `WorkerLaunchFailedError` typed | DONE |
| `job_state_consistency` | `Any` + getattr | P1 transitions | P1 | Type on `Job`/`Aisle` | DONE |
| ops CLIs `inspect_*` | getattr duck typing | P1 | P1 | Typed entity access | DONE |
| `sql_job_repository` mapping helpers | Mapping mixed in repo file | P1 | P1 | Extract `sql_job_row_mapper.py` | DONE |
| `sql_job_lease_predicates` | Duplicated CAS WHERE clauses | P1 | P1 | Shared predicate for UoW fence + complete/fail | DONE |
| Architecture import tests | No guard against application→FastAPI | P1 | P1 | Add architecture + fence characterization tests | DONE |
| `SqlJobRepository` full lease store split | God object ~1648 LOC | P0 | P2 | Mapper + predicates only; full store deferred | PARTIAL |
| `V3JobExecutor` path bodies | OCR/CODE_SCAN paths still large | P0 | P2 | Deferred (no OCR/CODE_SCAN changes in Phase 6) | DEFERRED |
| `V3JobFinalizationService` | Heavy finalize body | P1 | P2 | Deferred | DEFERRED |
| `AppContainer` provider split | Composition root still large | P1 | P2 | Deferred (no domain policy moved) | DEFERRED |
| `start_aisle_processing` settings getattr | Silent defaults | P1 | P2 | Deferred | DEFERRED |
| application→infrastructure imports | Catalogued | P1 | P2 | Incremental ports later | DEFERRED |
| Frontend/mobile | No Phase-6 structural blockers demonstrated | P3 | P3 | Out of scope this slice | NOT_STARTED |
| Dead code / vulture | Hygiene | P3 | P3 | Report only | DOCUMENTED |

## Deferred intentionally

Full `SqlJobLeaseStore` / executor path runners / AppContainer providers — high risk of CAS/TOCTOU or behavior drift; OCR/CODE_SCAN path extract blocked by Phase 6 scope rules.
