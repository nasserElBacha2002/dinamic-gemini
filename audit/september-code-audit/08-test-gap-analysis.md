# 08 — Test gap analysis

## Resultados ejecutados (VERIFIED)

| Suite | Resultado |
|-------|-----------|
| Backend pytest (full audit) | **5261 passed**, 4 skipped |
| Frontend vitest | **1300 passed**, 224 files |
| Mobile jest | **734 passed**, 82 suites |
| Audit tooling tests | No corridos aparte (`scripts/audit/tests/`) — NOT_RUN |

Cobertura backend reportada por pytest-cov en corrida: ~**79%** líneas (htmlcov). Cobertura ≠ riesgo AuthZ.

## Cobertura funcional (cualitativa)

| Área | Tests observados | Gap |
|------|------------------|-----|
| Auth login/JWT | Presentes | Refresh multi-instance / revocation |
| Tenant / company_admin IDOR list/get | Parcial (upload scope phase2, recognition config auth) | **List/get inventarios/clients sin matrix tenant** |
| Inventarios CRUD | Amplios | close/reopen N/A |
| Jobs start/cancel | Amplios | Chaos restart refresh |
| CODE_SCAN / labels | Unitarios densos | Cross-layer mobile↔backend parity exhaustiva |
| TXT import | Unitarios | Path traversal adversarial fuzz |
| ZIP package | Tests offline package | Zip-bomb / zip-slip matrix |
| Mobile offline sync | Jest core/services | Kill-app mid-sync E2E device |
| Frontend permisos URL | Component tests | Bypass solo-UI sin backend assert |

## Problemas de testing

| Tema | Clasificación |
|------|---------------|
| `security-exceptions.json` ausente rompe gate aunque tests pasen | OPS/TEST tooling |
| Mobile npm critical no bloquea gate (política progressive) | TEST-001 |
| Flaky SQL concurrent (histórico) | TEST-002 |
| Architecture auditors heurísticos (dead-code 1077 signals) | ruido / falsos positivos |
| DAST suites no ejecutadas | gap fase 2 |

## Tests que contradicen producto

No se demostró contradicción sistemática en esta fase. Documentación `PROJECT_CONTEXT` vs código: mayormente alineada; offline aisle sync vía ZIP es la divergencia de expectativa “sync aisle API”.
