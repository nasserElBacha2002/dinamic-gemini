# Legacy processing retirement audit (Phase 8 — Etapas A/B/C)

**Status:** audit + partial retirement (hide UX / block new writes).  
**Date:** 2026-07-20  
**Scope:** aisle identification modes, process modal, observability presentation, duplicate code-scan action.

## Classification legend

| Estado | Meaning |
|--------|---------|
| **ACTIVO** | Productive path for new work |
| **COMPATIBILIDAD HISTÓRICA** | Needed to read / display past jobs or configs |
| **OBSOLETO** | No consumers for new work; candidate for later removal |

---

## 1. Modes and strategies

| Valor | Tipo | Estado | Nuevos jobs | Notas |
|-------|------|--------|-------------|-------|
| `CODE_SCAN` | requested_mode / executed_strategy | ACTIVO | Sí (flag-gated) | Process modal option |
| `INTERNAL_OCR` | requested_mode / executed_strategy | ACTIVO | Sí (flag-gated) | Process modal option |
| `LEGACY_LLM` | mode / strategy | COMPATIBILIDAD HISTÓRICA | No (override/config blocked) | Inherited system default may still run until migrated |
| `LEGACY_LLM_TEMPORARY` | executed_strategy | COMPATIBILIDAD HISTÓRICA | Indirect via disabled flags | Flag-off fallback path |
| `EXTERNAL_PROVIDER` | future naming | — | Not primary UX yet | Mapped conceptually from legacy LLM |

**System default (new jobs):** `INTERNAL_OCR`. Effective `LEGACY_LLM` after inheritance is **blocked** at job start. Historical jobs remain readable; historical retries may re-execute LEGACY snapshots (explicit residual path).

**Resolution chain (effective mode):** request override → aisle → inventory → client → system default (`INTERNAL_OCR`).

**Status:** partial retirement — new effective LEGACY blocked; enums/columns retained for history.

---

## 2. Inventory (selected)

| Nombre | Tipo | Ubicación | Consumidores | Estado | Reemplazo | Riesgo eliminación | Acción |
|--------|------|-----------|--------------|--------|-----------|--------------------|--------|
| `LEGACY_LLM` enum | domain | `backend/src/domain/aisle_identification/modes.py` | jobs, resolvers, UI labels | COMPATIBILIDAD | `INTERNAL_OCR` / `CODE_SCAN` / external | Alto — historical jobs | KEEP + read-only |
| `legacy_processing_guard` | service | `backend/src/application/services/legacy_processing_guard.py` | update client/inventory/aisle; start processing | ACTIVO (retirement) | — | Bajo | KEEP |
| Process modal LEGACY option | UI | removed from selector | — | OBSOLETO (hidden) | business options | Bajo | HIDDEN (Etapa C) |
| Observability AI-centric tabs | UI | `AisleObservabilityWorkspace` | operators | ACTIVO (gated) | presentation mapper | Medio | CONDITIONAL |
| `ProcessingExecutionPresentationMapper` | FE mapper | `frontend/src/features/processing/mappers/processingExecutionPresentation.ts` | dialog, obs, header | ACTIVO | — | Bajo | KEEP |
| Más acciones → Escanear códigos | UI | `AisleResultsHeader` | was opening CodeScanDrawer | OBSOLETO (entry removed) | Process → CODE_SCAN | Medio | REMOVED entry |
| `/v3/.../code-scans/run` | API | `backend/src/api/routes/v3/code_scans.py` | CodeScanDrawer, evidence | COMPATIBILIDAD | job CODE_SCAN strategy | Alto if deleted now | DEPRECATE later (Etapa E) |
| `finalize_code_scan_success` stage `CodeScan` | worker | `v3_job_execution_state` | OCR jobs showed wrong stage | ACTIVO (fixed) | `InternalOcr` when OCR | Bajo | FIXED |
| Feature flags CODE_SCAN/OCR | env | `.env.example` | worker routing | ACTIVO | — | Alto | KEEP (rollback) |
| In-process legacy metrics | counters | `legacy_processing_guard` | ops soak | ACTIVO (temp) | Prometheus later | Bajo | KEEP until Etapa F |

---

## 3. Actions matrix

| Acción | Scope | Crea job | Estrategia | Reemplazo |
|--------|-------|----------|------------|-----------|
| Procesar pasillo | aisle | Sí | selected / inherited | Primary |
| CODE_SCAN from Procesar | aisle | Sí | CODE_SCAN | Primary for barcodes |
| Más acciones → Escanear códigos | aisle | No (sync pyzbar run) | auxiliary table | Entry removed; API kept |
| Evidence / review signals | position | No | read-only | KEEP |
| Reprocesar / retry job | job | Sí (retry) | modern mode required | KEEP |

---

## 4. Etapas B/C implemented in this change

1. **Block new configs** with `LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION`.
2. **Block explicit process override** `LEGACY_LLM` on start.
3. **Hide** legacy options from process modal; business labels.
4. **Conditional** provider/model/prompt in observability.
5. **Remove** Más acciones → Escanear códigos entry.
6. **Correct** OCR current stage presentation (`CodeScan` → `InternalOcr`).

**Not done (later):** auto-migrate DB configs (D), delete `/code-scans/run` (E), drop flags/columns (F).

---

## 5. Rollback

- Re-enable legacy MenuItem in process dialog (git revert FE).
- Remove guard calls from update/start use cases (git revert BE).
- Re-add Más acciones code-scan MenuItem.
- Feature flags for CODE_SCAN/OCR remain available for worker rollback.

## 6. Mapping policy (Etapa D — dry-run only)

Configurable suggestion (not auto-applied):

```text
LEGACY_LLM → INTERNAL_OCR   # when OCR flags on and tenant ready
LEGACY_LLM → AUTO/inherit   # when product wants pipeline default
LEGACY_LLM → EXTERNAL_PROVIDER  # naming only when external-direct UX ships
```

Require per-tenant dry-run SQL report before writes.
