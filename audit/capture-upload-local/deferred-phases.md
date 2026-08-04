# Local processing / CSV / security — status vs HEAD

**HEAD date:** 2026-08-04  
**Scope:** Capture finish, local completion, CSV export/import, freeze snapshot, upload policy.

| Área | Estado real en HEAD (working tree) |
|------|-------------------------------------|
| Fase 0–1 finish instrumentation + MediaStore safe check | Implementado |
| Freeze snapshot (`capture_session_freezes` / v23) | Implementado (corrección estructural) |
| Fase 2 prepare parallelism | Implementado |
| Fase 3 `local_completed` + upload policies MANUAL/WHEN_CONNECTED/NOW | Implementado (corrección) |
| Fase 4 mobile CSV export | Implementado; `source` = detection provenance |
| Fase 5 backend CSV import | Preview + confirm productivo + `ingestion_source`; migración **0086** |
| Fase 6 local↔remote reconciliation | Solo clasificador puro — **no completa**; flag apagado |
| Fase 7 signed URLs | Explicitamente diferido |

## Issues abiertos

- Integración SQL Server concurrente / migrate apply-rollback 0086 en CI
- Tenant company/client en CSV aún metadata comparativa (mobile wiring desde auth parcial)
- E2E Android build + baseline S10+ performance
- Working tree no limpio hasta commit explícito

## Tests de referencia

- Backend: `pytest -q tests/unit/test_local_csv_import.py tests/unit/test_local_csv_mobile_contract.py`
- Mobile: `npm run typecheck`, `captureService` / `localCsv` / migrations tests
