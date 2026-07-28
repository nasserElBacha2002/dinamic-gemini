# Phase 3 — Worker lease lifecycle

Flujo del worker v3: **claim → heartbeat → loss → halt** (sin FAIL por fencing).

## 1. Claim (prep)

`V3JobPreparationService`:

1. Genera `claim_owner_id = uuid4()`.
2. Lee `JOB_LEASE_DURATION_SEC`.
3. `mark_running` → `try_claim_starting_to_running(..., lease_duration_seconds)`.
4. Si `may_execute` falso → halt (Phase 1 conflict); sin ejecución.
5. Si acquire → `V3PreparationResult` incluye **`lease: JobLease`**.

## 2. Monitoring / heartbeat

`V3JobExecutor` construye `V3JobMonitoringRequest` con:

- `lease=prep.lease`
- `lease_extension_seconds=job_lease_duration_sec`
- intervalo loop ≈ `job_lease_heartbeat_interval_sec`

`V3JobMonitoringService.session`:

```text
loop cada heartbeat_interval:
  heartbeat_with_lease(active_lease, extension_seconds)
  if outcome != RENEWED:
      log event=job_lease_lost
      runtime_abort_event.set()
      stop heartbeat
      break   # NO fail_job_and_aisle
  else:
      active_lease = renew.lease  # expiry actualizado, mismo token
```

Si `lease is None` → legacy `heartbeat()` unfenced (no Phase 3 path preferido).

## 3. Ejecución protegida

Mientras corre pipeline / CODE_SCAN / OCR:

- Checks de `runtime_abort_event` en loops.
- `merge_result_json_protected(..., lease=lease)` para progress / outcomes.
- Finalization / `finalize_code_scan_success(..., lease=lease)`.
- Fail paths pueden pasar `lease` a `fail_job_and_aisle` → `fail_if_leased`.

## 4. Lease loss → halt

| Señal | Efecto |
|---|---|
| Renew miss en heartbeat | `runtime_abort_event`; no FAIL |
| `JobLeaseLostError` en merge/finalize | catch → log `job_lease_lost` → return/halt |
| Abort antes de finalize | log `runtime_abort_before_finalize`; skip success finalize |

El job puede seguir `RUNNING` bajo **otro** owner tras steal, o quedar hasta stale reclaim Phase 1.

## 5. Diagrama de secuencia

```text
Prep                    Repo                 Monitoring              Executor
 |--claim+lease-------->|                     |                       |
 |<--JobLease-----------|                     |                       |
 |----------------------|--session(lease)---->|                       |
 |                      |<--renew CAS---------|                       |
 |                      |                     |--runtime handles----->|
 |                      |<--merge if leased---|<----progress----------|
 |                      |                     |                       |
 |                      |X--renew LOST--------|                       |
 |                      |                     |--abort.set----------->|
 |                      |                     |                       | halt (no FAIL)
```

## 6. Invariantes del lifecycle

1. Solo el worker con lease vigente debe mutar `result_json` / completar vía APIs fenced.
2. Loss ⇒ stop local; **no** `FAILED` por fencing.
3. `fencing_token` en logs de loss para auditoría.
4. Cancel API / unfenced saves fuera de este lifecycle (gap documentado).
