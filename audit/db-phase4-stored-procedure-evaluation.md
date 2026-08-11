# Fase 4 — Evaluación de Stored Procedures basada en evidencia

**Resultado:** `NO_ACTION_REQUIRED`  
**Fecha:** 2026-08-11  
**Stored Procedures before Phase 4:** 0  
**Stored Procedures added:** 0  
**Stored Procedures total:** 0  
**Triggers added:** 0  
**New migrations:** 0  

---

## Executive summary

```text
PHASE_4: NO_ACTION_REQUIRED
```

Tras auditar confirm (package/CSV), claim D1, job/worker/outbox claims y locking de migraciones, **ningún flujo supera el umbral beneficio/riesgo** para introducir una Stored Procedure de aplicación.

La arquitectura actual ya aplica, en orden:

```text
Constraint → Index → Backend transaction → Set-based / batch SQL
```

Los hot paths de claim de cola ya usan `UPDATE … OUTPUT` en un solo statement. Package/CSV confirm ya son atómicos en una transacción APPLY (Fase 1), con storage fuera de locks y batch medido (Fase 2). Encapsular eso en un SP **no reduce races demostrables**, **duplicaría política de dominio (SKIP/REJECT)** y **rompería** el split PLAN → STAGE → APPLY.

**Métrica honesta:** las mediciones de Fase 2 cuentan **Python cursor calls** y **wall-clock**. **No** se afirmaron network RPCs. En esta fase tampoco se inventan RPCs: `cursor.execute` ≠ round trip de red sin medición wire-level.

`NO_ACTION_REQUIRED` es un resultado exitoso: **0 SPs** no es una deficiencia arquitectónica.

---

## Decision hierarchy (aplicada)

| Capa | ¿Suficiente para candidatos auditados? |
| ---- | -------------------------------------- |
| Constraint / unique index | Sí (D1 `UQ_icpl_aisle_label`, productive secondary keys) |
| Index | Sí (ya existentes; sin SP) |
| Backend transaction | Sí (package APPLY, CSV confirm, job STARTING→RUNNING) |
| Set-based / batch SQL | Sí (Fase 2 `executemany` / `fast_executemany` productivo) |
| View / function | No necesaria |
| **Stored Procedure** | **No justificada** |
| Trigger | Fuera de alcance (Fase 5 si aplica) |

---

## Candidates

| ID | Flow | Current architecture | Evidence | Decision |
| -- | ---- | -------------------- | -------- | -------- |
| P4-1 | Package confirm PLAN→STAGE→APPLY | 1 APPLY TX; UPDLOCK package→CSV; storage fuera de locks | Fase 1 failure matrix A–H; Fase 2 PLAN→APPLY race | **NO_ACTION** |
| P4-2 | CSV confirm | 1 TX; set-based productive + persist | Fase 2 benches 10/100/1000; cursor calls ↓ | **NO_ACTION** |
| P4-3 | D1 counted label claim | 1 INSERT + unique violation | `UQ_icpl_aisle_label`; concurrency tests | **NO_ACTION** |
| P4-4a | `claim_next_queued_job` | CTE + `UPDATE…OUTPUT` + UPDLOCK READPAST | Ya single-statement | **NO_ACTION** |
| P4-4b | `try_claim_starting_to_running` | Multi-stmt TX (job+aisle+lease CAS) | Outcomes tipados en Python; baja frecuencia vs poll | **NO_ACTION** (LOW wrap-only, ROI insuficiente) |
| P4-4c | Asset command claim | `UPDATE…OUTPUT` | Single statement | **NO_ACTION** |
| P4-4d | Outbox `claim_due_entries` | CTE + `UPDATE…OUTPUT` | Single statement | **NO_ACTION** |
| P4-4e | Outbox `claim_entry` | SELECT UPDLOCK + versioned UPDATE | Policy en Python | **NO_ACTION** |
| P4-5 | Migration / image `sp_getapplock` | SP **nativo** SQL Server | Deploy / short coordination | **Not an app SP candidate** |
| P4-6 | Inventory status CAS / reconcile | `UPDATE … WHERE status = ?` + verify-after-write | Fase 3 | **NO_ACTION** |

### Inventory table (detail)

| ID | Flow | Current DB calls (approx, hot path) | Transaction | Concurrency mechanism | Volume | Candidate SP | Class |
| -- | ---- | ----------------------------------: | ----------- | --------------------- | -----: | ------------ | ----- |
| P4-1 | Package confirm | PLAN ~5–10; APPLY ~12–25+ (chunks) | PLAN rollback + APPLY 1 commit | UPDLOCK package→CSV; UQ productive | Low (user confirm) | No | NO_ACTION |
| P4-2 | CSV confirm | ~8–20+ | 1 TX (o nested en package cursor) | UPDLOCK import; UQ; SKIP/REJECT Python | Low–med | No | NO_ACTION |
| P4-3 | D1 try_claim | 1 INSERT | Caller / autocommit | Unique index | Med (per label) | No | NO_ACTION |
| P4-4a | claim next job | 1 UPDATE OUTPUT (+ optional get) | Implicit | UPDLOCK READPAST | High poll | No | NO_ACTION |
| P4-4b | STARTING→RUNNING | 4–5 in TX | Explicit | Row locks + CAS + lease | Once/job | Wrap-only | LOW → reject |
| P4-4c | Asset claim | 1 UPDATE OUTPUT | Single stmt | Status / READPAST | Med | No | NO_ACTION |
| P4-4d | Outbox due claim | 1 UPDATE OUTPUT | Single stmt | READPAST | Med | No | NO_ACTION |
| P4-5 | Migration applock | N/A | Session | Native `sp_getapplock` | Deploy | N/A | Note only |

---

## Measurements

### Reused from Phase 2 (productive INSERT path)

Source: `audit/db-phase2-set-based-performance.md` (SQL Server test DB, 2026-08-11).

| n | row-by-row ms | executemany (fast=False) ms | executemany (fast=True) ms |
| -: | ------------: | --------------------------: | -------------------------: |
| 10 | 6.8 | 6.4 | 7.7 |
| 100 | 34.5 | 29.7 | 10.0 |
| 1000 | 306.8 | 292.3 | 82.7 |

Cursor-call shape (100 rows): ~200 `execute` → ~2 batch calls. **Network RPCs: not measured → not asserted.**

### Phase 4 SP vs backend

**No SP prototype measured** — no candidate reached HIGH/MEDIUM with a strong A–D justification. Running CURRENT vs SP without a justified design would invent a “winner.”

### ROI threshold examples applied

| Scenario | Verdict |
| -------- | ------- |
| Wrap package APPLY in SP with same TX semantics | Cosmetic; domain SKIP/REJECT + STAGE callback stay in Python → **NO_ACTION** |
| SP for D1 INSERT | Already 1 statement + constraint → **NO_ACTION** |
| SP for `claim_next_queued_job` | Already 1 statement → **NO_ACTION** |
| Hypothetical 5% faster on once-per-day confirm | **NO_ACTION** even if measured |

---

## Concurrency analysis

| Flow | Mechanism | SP needed? |
| ---- | --------- | ---------- |
| Package dual confirm | 2 connections; unique productive + status CAS (Fase 1 D) | No |
| PLAN→APPLY secondary-key race | Unique index + revalidation (Fase 2) | No |
| D1 dual claim | `UQ_icpl_aisle_label` | No |
| Job queue claim | UPDLOCK READPAST + OUTPUT | No |
| Inventory reconcile | CAS + verify-after-write (Fase 3) | No |

No measured lock-contention profile showed a multi-step race that **only** an SP (vs current TX + constraints) closes.

---

## Transaction analysis

### Package confirm (P4-1) — deep audit

```text
Optimistic gate
→ PLAN TX (UPDLOCK, resolve rows_to_import, ROLLBACK)
→ STAGE storage/SourceAssets (fuera de locks SQL)
→ APPLY TX (UPDLOCK package → CSV; productive + CSV CONFIRMED + package CONFIRMED; 1 COMMIT)
→ post-commit materialize (retryable)
```

| Question | Answer |
| -------- | ------ |
| ¿Cuántas llamadas SQL en APPLY? | Varias (locks, selects, batch inserts/updates); **una** TX |
| ¿Round trips medidos? | No (solo cursor/wall-clock en Fase 2) |
| ¿Lock order package → CSV suficiente? | Sí (documentado + tests A–H) |
| ¿SP reduciría una race? | No evidencia; constraints + APPLY ya cubren |
| ¿Rompería storage fuera de locks? | Sí, si se unifica STAGE dentro del SP/TX larga |
| ¿Duplicaría conflict logic? | Sí (SKIP/REJECT / DUPLICATE en dominio) |

**Default esperado cumplido:** `NO_ACTION`.

### CSV confirm (P4-2)

Una TX (standalone o cursor del package). Batch set-based ya en writer + `_persist`. Multi-statement **dentro** de TX bajo UPDLOCK del import; races cross-import → unique index, no SP.

### Job claim (P4-4)

Antes de SP se evaluó `UPDATE…OUTPUT`: **ya está** en poll paths. `try_claim_starting_to_running` es multi-statement **por** branching de outcomes (`NOT_FOUND`, `TARGET_MISMATCH`, `TERMINAL`, aisle eligibility, lease) — moverlo a T-SQL duplica workflow en DB.

### Migration locking (P4-5)

Uso de `sp_getapplock` en `migrations/service.py` (y applock de imagen) = **SP nativo de plataforma**, no justifica crear SPs de aplicación. Sin cambio.

---

## Selected SPs

```text
(none)
```

---

## Rejected SPs

| Candidate | Reason |
| --------- | ------ |
| `usp_local_package_confirm` | APPLY ya 1 TX; STAGE debe quedar fuera; dominio SKIP/REJECT en Python; sin bottleneck medido |
| `usp_local_csv_confirm` | Idem + set-based ya en repos; SP encapsularía SQL parametrizado existente |
| `usp_icpl_try_claim` | 1 INSERT + UQ; estética ≠ ROI |
| `usp_claim_next_job` | Ya CTE+UPDATE OUTPUT |
| `usp_try_claim_starting_to_running` | Solo bundling; outcomes de dominio; frecuencia baja vs poll |
| `usp_outbox_claim_*` | Ya OUTPUT / versioned UPDATE |
| Inventory status repair SP | CAS + verify-after-write en Python (Fase 3); reglas derive puras en dominio |

---

## Migration impact

```text
New migrations: 0
HEAD remains: 0095
```

No `CREATE PROCEDURE`. No cambio de permisos EXECUTE.

---

## Test evidence

Regression suite (Fase 4 sin SPs):

```bash
cd backend

.venv/bin/python -m pytest \
  tests/integration/db_integrity/ \
  tests/integration/local_inventory_package/ \
  tests/integration/local_csv_batch/ \
  tests/integration/inventory_status/ \
  tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py \
  --tb=line --no-cov -q
```

(Resultados exactos en `audit/phase4-stored-procedure-evaluation-validation.md`.)

No se creó `tests/integration/stored_procedures/` — no hay SP que cubrir.

---

## Residual risks / follow-ups (no Phase 4 SP work)

1. **Wire-level RPC instrumentation** (si en el futuro se necesita afirmar round trips de red).
2. Posible micro-optimización app: evitar segunda query de secondary keys en confirm CSV (no SP).
3. Cualquier hallazgo tipo **trigger** → documentar para Fase 5; no implementar ahora.
4. Revisitar SPs **solo** si métricas futuras de contention/RPC muestran un cuello que constraints+TX+batch no resuelven.

---

## Backend vs DB ownership (reafirmado)

| Backend | DB |
| ------- | -- |
| Authorization, domain, workflow, SKIP/REJECT policy | Constraints, locks, CAS, set ops, claim primitives |
| OCR / CV / LLM / storage / external APIs | Persistence integrity |

Ningún SP propuesto habría movido ownership de forma saludable.

---

## Phase rollup

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
PHASE_3: COMPLETE
PHASE_4: NO_ACTION_REQUIRED

Stored Procedures before Phase 4: 0
Stored Procedures added: 0
Stored Procedures total: 0
Triggers added: 0
New migrations: 0
```

## Principio

```text
Si Python + constraints + transacciones + set-based SQL
resuelven correctamente el problema → mantener Python.

La ausencia de Stored Procedures no es una deficiencia arquitectónica.
```
