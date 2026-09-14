# 07 — Quality and correctness review

## Bugs / gaps funcionales (VERIFIED)

| ID sugerido | Tema | Evidencia |
|-------------|------|-----------|
| FUNC-001 | Sin close/reopen inventario | Solo write_policy sobre estados derivados |
| FUNC-002 | Offline aisle sync vía ZIP no CREATE_AISLE | mobile offline ops types |
| FUNC-003 | FE review-queue redirect muerto vs API review viva | `ReviewQueueRedirect` |
| FUNC-004 | Refresh tokens no sobreviven restart | `auth/service.py` in-memory |
| FUNC-005 | Dual mobile queues / flags | `featureFlagCompatibility.ts` |

## Concurrencia / idempotencia / jobs

| Tema | Evaluación |
|------|------------|
| Job claim SQL + leases | IMPLEMENTED — diseño sólido (VERIFIED existencia) |
| Upload spool auth order | Tests dedicados phase2 capture upload |
| Persistencia code-scan | Locks + coverage uniqueness (persister) |
| Test flaky observado históricamente | `test_sql_concurrent_overlapping_sets` — flaky local en corridas previas; en full audit pytest **pasó** 5261 |

## Errores / logging

- Broad `except Exception` frecuente (457 matches heurísticos en `backend/src`) — deuda **MEDIUM** (ARCH/QUAL).
- Bandit medium=102 (assert/hardcoded, etc.) — revisar selectivamente; **0 HIGH**.

## Fail-open vs fail-closed

- Tenant binding: fail-closed para uploads con policy.
- List/get inventarios: fail-open respecto a tenant (gap AuthZ).
- Legacy LLM starts: fail-closed via guard.

## Defaults inseguros / config

- Docs OpenAPI on by default.
- Embedded worker default on (ops), `./dev.sh` lo desactiva — documentado README.

## Código muerto / legacy

LEGACY_LLM, INTERNAL_OCR, redirects FE, páginas huérfanas — DEAD_CODE/LEGACY inventario en §04.
