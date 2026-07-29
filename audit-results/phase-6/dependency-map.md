# Phase 6 — Dependency map

```text
domain
  ↑
application (ports, use cases, services)
  ↑
infrastructure / api / scripts / runtime (AppContainer)
```

## Enforced

| Rule | Mechanism |
| ---- | --------- |
| application ↛ FastAPI/Starlette | `test_application_does_not_import_fastapi` |
| domain ↛ infrastructure/api/database | `test_domain_does_not_import_infrastructure_or_api` |
| Persist fence without getattr | `test_persist_aisle_result_does_not_getattr_fence` |
| Protocol declares fence | `test_job_result_uow_protocol_declares_fence_job_lease` |

## Known residual coupling (deferred)

- Some application services still import infrastructure adapters (catalogued; not rewritten this phase).
- Routers still resolve use cases via `AppContainer` (composition root — acceptable).
- Scripts/ops CLIs thin-adapt to `RecoverStaleJobUseCase` (already single use case).
