# Fase 5 — Evaluación excepcional de Triggers SQL Server

**Resultado:** `NO_ACTION_REQUIRED`
**Fecha:** 2026-08-11
**Stored Procedures total:** 0 (sin cambios vs Fase 4)
**Triggers before Phase 5:** 0
**Triggers added:** 0
**Triggers total:** 0
**New migrations:** 0
**Migration HEAD:** `0095`

---

## Executive summary

```text
PHASE_5: NO_ACTION_REQUIRED
```

Auditoría sistemática de invariantes que *podrían* pedirse vía Trigger. Ningún candidato cumple los criterios A–I de aprobación (§19 del plan). Constraints, unique indexes, transacciones explícitas, CAS y el reconciler de Fase 3 ya cubren integridad y recuperación.

**Principio aplicado:** Trigger = último recurso. Preferir CHECK / FK / UNIQUE / TX / CAS / set-based / (SP rechazados en Fase 4) antes que lógica invisible en DB.

La ausencia de Triggers es un resultado exitoso.

---

## Existing trigger baseline

### Repo

```text
CREATE TRIGGER / ALTER TRIGGER / AFTER INSERT|UPDATE|DELETE / INSTEAD OF
→ 0 matches under backend/ (migrations + schema + Python)
```

### Live SQL Server catalog (test DB, 2026-08-11)

```sql
SELECT s.name, t.name, tr.name, tr.is_disabled
FROM sys.triggers tr
JOIN sys.objects t ON t.object_id = tr.parent_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE tr.parent_class = 1;
```

```text
TRIGGER_COUNT = 0
Application triggers before Phase 5: 0
Application triggers after Phase 5: 0
```

### Migration HEAD

```text
get_required_schema_version() → 0095
Last UP: 0095_aisle_scoped_counted_product_labels.sql
```

---

## Candidate inventory

| ID | Invariante | Tablas | Mecanismo actual | Riesgo sin trigger | Alternativa | Trigger ROI | Decisión |
| -- | ---------- | ------ | ---------------- | ------------------ | ----------- | ----------- | -------- |
| T1 | `Inventory.status` = f(aisles activas) | inventories, aisles | Pure derive + reconciler CAS + verify-after-write + backfill | Drift temporal hasta repair | Mantener reconciler | Negativo (deadlock) | **NO_ACTION** |
| T2 | `COMPLETED` ↔ `completed_at` | inventories | CAS + repair metadata | Metadata inconsistente ocasional | Preferir **CHECK** (follow-up) | Bajo | **NO_ACTION** |
| T3 | `updated_at` automático | muchas | Clock / writes explícitos | Stamp omitido si bug app | Disciplina app | Bajo | **NO_ACTION** |
| T4 | Soft delete / `is_active` cascade | aisles (+ hijos) | Domain deactivate + scope | Ops sobre inactivos bloqueadas en UC | Política app | Bajo | **NO_ACTION** |
| T5 | D1 label único por aisle | inventory_counted_product_labels | `UQ_icpl_aisle_label` | Ninguno si índice vivo | Unique index | Nulo | **NO_ACTION** |
| T6 | Idempotency uniqueness | source_assets, labels, … | Filtered UNIQUE | Race → unique violation | Unique index | Nulo | **NO_ACTION** |
| T7 | Package/CSV status propagation | packages, csv imports | APPLY TX + post-commit aisle | Drift post-commit | TX + reconcile | Negativo | **NO_ACTION** |
| T8 | SourceAsset lifecycle | source_assets | Repos + UQ upload | Orphans operativos | App + unique | Bajo | **NO_ACTION** |
| T9 | job.status → aisle.status | inventory_jobs, aisles | Same-TX claim/stale | Split brain si se saltea TX | Multi-stmt TX | Negativo | **NO_ACTION** |
| T10 | Lease expiration | jobs, outbox, … | Poller / stale reconciler | Stale hasta poll | App reclaim | Negativo | **NO_ACTION** |
| T11 | Outbox event generation | artifact_publication_outbox | Enqueue explícito en finalization | Evento omitido si bug | Outbox pattern app | Negativo | **NO_ACTION** |
| T12 | Audit trail forense | review_actions, events | Writes explícitos | Audit incompleto | Domain events | Negativo | **NO_ACTION** |

---

## Trigger decision criteria

Un Trigger solo se aprueba si se cumplen **todas**:

| # | Criterio | Resultado en esta fase |
| - | -------- | ---------------------- |
| A | Invariante de persistencia/DB | Parcial en T2/T5/T6; dominio en T1/T7/T9 |
| B | Debe valer para cualquier writer | Solo relevante si hay writers externos (no demostrados) |
| C | No expresable con CHECK/FK/UNIQUE/TX/CAS | Falla en todos los candidatos |
| D | Sin workflow/domain policy | Falla en T1/T7/T9/T11 |
| E | Sin servicios externos | Storage/queue fuera de SQL |
| F | Sin side effects fuera de SQL Server | T8 storage fuera |
| G | Multi-row correcto | N/A (no SP/Trigger) |
| H | Tests concurrencia/rollback | N/A |
| I | Beneficio > costo de invisibilidad | Falla (especialmente T1 deadlock) |

---

## Candidate analysis

### T1 — Inventory.status rollup — `NO_ACTION`

**File / mechanism:**
`backend/src/application/services/inventory_status_reconciler.py` (`repair`)
`backend/src/domain/inventory/derive_status_from_aisles.py`
`backend/src/infrastructure/repositories/sql_inventory_repository.py` (`compare_and_set_status`)

**Reasons:**
- Estado derivado de dominio (prioridades FAILED → PROCESSING → IN_REVIEW → COMPLETED → …).
- Scope operativo excluye aisles inactivas (`scope_from_aisles`).
- Trigger `AFTER … ON aisles → UPDATE inventories` **duplicaría** la función pura Python.
- Eventual consistency + detect/backfill ya son el diseño explícito de Fase 3.
- **Deadlock:** ver sección concurrency (aisle→inventory vs inventory→aisle).

### T2 — completed_at ↔ COMPLETED — `NO_ACTION`

**Reasons:**
- CAS ya escribe `status` + `completed_at` juntos.
- Repair metadata-only (Fase 3 tests A/B) recupera drift.
- Un **CHECK** declarativo es mejor que Trigger si se endurece luego (`FOLLOW_UP_CONSTRAINT`).
- Trigger no repara datos históricos; backfill sí.

### T3 — updated_at automation — `NO_ACTION`

**Reasons:**
- Timestamps de dominio / Clock inyectado en tests.
- Trigger `GETUTCDATE()` oculta writes y pelea optimistic concurrency.
- Comodidad ≠ invariante de integridad.

### T4 — soft delete propagation — `NO_ACTION`

**Reasons:**
- `is_active` / deactivate es lifecycle de producto, no FK física.
- Agregaciones ya filtran inactivos.
- Cascade trigger escondería política y sorprendería jobs/uploads.

### T5 — D1 counted labels — `NO_ACTION`

**Reasons:**
- Autoridad: `UQ_icpl_aisle_label` (migration `0095`).
- `try_claim` = INSERT + unique violation.
- Trigger no supera UNIQUE.

### T6 — Idempotency uniqueness — `NO_ACTION`

**Reasons:**
- Filtered UNIQUE indexes (p.ej. upload idempotency `0044`, label client keys).
- Constraint tiene prioridad absoluta sobre Trigger “anti-duplicados”.

### T7 — Package / CSV state — `NO_ACTION`

**Reasons:**
- Fase 1: APPLY = 1 TX (productive + CSV + package).
- STAGE storage fuera de locks a propósito.
- Propagar estados vía Trigger rompería SKIP/REJECT en Python y observabilidad.

### T8 — SourceAsset lifecycle — `NO_ACTION`

**Reasons:**
- SQL no controla filesystem / object storage.
- Cleanup/orphan policy es backend/jobs (Fase 2).

### T9 — job → aisle — `NO_ACTION`

**Reasons:**
- Ya same-TX en `try_claim_starting_to_running` / stale reclaim.
- Outcomes tipados (`JobClaimOutcome`) son workflow, no integridad relacional pura.
- Trigger duplicaría política y arriesga ciclos de lock.

### T10 — leases — `NO_ACTION`

**Reasons:**
- Expiración es **tiempo**; Triggers solo corren ante DML, no son scheduler.
- `JobStaleReconciler` / release expired claims ya cubren.

### T11 — outbox — `NO_ACTION`

**Reasons:**
- Enqueue explícito junto a finalización (mismo patrón transaccional app).
- Trigger automático pelearía checksums/versioning/dispatcher.
- No hay evidencia de writers externos obligados a emitir outbox.

### T12 — audit trail — `NO_ACTION`

**Reasons:**
- No hay requisito regulatorio vigente de audit trail DB immutable en este alcance.
- Logs de aplicación ≠ forense DB.
- No inventar tabla/trigger de auditoría genérica.

---

## Constraint alternatives

| Candidate | Mejor alternativa |
| --------- | ----------------- |
| T1 Inventory.status | Reconciler + CAS + detect/backfill |
| T2 completed_at | CAS actual; opcional CHECK (follow-up) |
| T3 updated_at | Writes explícitos |
| T4 soft delete | Domain + query filters |
| T5 D1 | Unique index |
| T6 idempotency | Unique / filtered unique |
| T7 package/CSV | Backend TX (Fase 1) |
| T8 SourceAsset | App lifecycle + UQ |
| T9 job→aisle | Explicit multi-stmt TX |
| T10 leases | Poller / stale reconciler |
| T11 outbox | Explicit outbox row |
| T12 audit | Domain events / review_actions |

### FOLLOW_UP_CONSTRAINT (fuera de alcance Fase 5)

```text
CK_inventories_completed_at_matches_status (conceptual):
  (status = 'completed' AND completed_at IS NOT NULL)
  OR (status <> 'completed' AND completed_at IS NULL)
```

Antes de migrar: validar filas históricas + backfill. **No** Trigger. **No** P0 bloqueante (repair ya existe).

---

## Concurrency / deadlock analysis

### Contra Trigger aisle → inventory (T1)

```text
TX-Claim / stale (worker):
  UPDLOCK inventory_jobs
  → UPDLOCK aisles
  → UPDATE aisles
  → [TRIGGER] XLOCK inventories   # orden aisle → inventory

TX-Reconcile:
  UPDATE inventories WHERE status = ?   # XLOCK inventory
  → SELECT aisles (verify-after-write)  # necesita SLOCK aisle
```

Orden cruzado → riesgo de deadlock 1205 bajo carga claim + reconcile.

El diseño actual **evita** actualizar inventory dentro de TXs que ya tienen aisle X-lock; usa CAS optimista sin locks largos de aisle.

### Otros

- Package confirm: package → CSV (sin trigger de status inventory).
- Job claim: job → aisle en una TX (sin trigger inverso).

---

## Selected triggers

```text
(none)
```

---

## Rejected triggers

Todos los de la matriz (T1–T12) → `NO_ACTION`.
Ningún candidato HIGH/MEDIUM con ROI positivo.

---

## Migration impact

```text
New migrations: 0
HEAD remains: 0095
Stored Procedures added in Phase 5: 0
```

---

## Test evidence

Regressions (sin código productivo nuevo):

```bash
cd backend
.venv/bin/python -m pytest \
  tests/integration/db_integrity/ \
  tests/integration/inventory_status/ \
  tests/integration/local_inventory_package/ \
  tests/integration/local_csv_batch/ \
  tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py \
  --tb=line --no-cov -q
```

(Resultados exactos en `audit/phase5-trigger-evaluation-validation.md`.)

---

## Residual risks

1. Drift temporal de `inventory.status` hasta repair/backfill — **aceptado** (Fase 3).
2. CHECK `completed_at` aún no existe — follow-up opcional, no Trigger.
3. Si en el futuro aparecen writers SQL ad-hoc fuera del backend, reevaluar constraints primero, Triggers solo si A–I se cumplen.

---

## Final status

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
PHASE_3: COMPLETE
PHASE_4: NO_ACTION_REQUIRED
PHASE_5: NO_ACTION_REQUIRED

Stored Procedures total: 0
Triggers before Phase 5: 0
Triggers added: 0
Triggers total: 0
New migrations: 0
```

## Principio

```text
Un Trigger solo debe existir cuando la base de datos
es inequívocamente el lugar correcto para esa invariante
y ninguna primitive declarativa más simple puede garantizarla.

Si existe una solución explícita, testeable y observable
mediante constraints + transactions + backend,
preferir esa solución.
```
