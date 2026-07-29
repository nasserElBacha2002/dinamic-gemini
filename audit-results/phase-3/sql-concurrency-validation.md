# Phase 3 — SQL concurrency validation

Cómo `backend/tests/integration/jobs/test_sql_job_lease_fencing.py` valida lease fencing contra **SQL Server real** (no mocks).

## Prerrequisitos

- Pytest marker `integration`.
- Fixture `sql_client` → `sql_server_client_or_skip(...)`; skip si no hay ODBC / connection string.
- Fixture `_require_lease_columns`: exige columnas `lease_fencing_token`, `lease_expires_at`, `lease_acquired_at`, `claim_owner_id`; skip con mensaje de aplicar **migration 0072**.
- Seed: inventory + aisle + job `STARTING` vía repos SQL reales.

## Escenarios

| Test | Qué valida |
|---|---|
| `test_sql_monotonic_fencing_token` | Claim → token `1`; tras expiry, `reacquire` → token `2` (`>` prev) |
| `test_sql_stale_heartbeat_rejected` | Tras steal, `renew_lease` del lease viejo → `LEASE_LOST` |
| `test_sql_stale_result_write_rejected` | Merge con lease stale → `LEASE_LOST` y sin patch; lease actual aplica `{"ok": True}` |
| `test_sql_stale_finalization_rejected` | `complete_if_leased` stale no cambia status (sigue RUNNING); owner actual puede SUCCEEDED |
| `test_sql_dual_connection_lease_steal` | Dos `SqlJobRepository` + threads + `threading.Barrier`; exactamente 1 `ACQUIRED`, 1 `CONFLICT`, token `[2]` |

## Mecánica de concurrencia (steal dual)

1. Owner A claim con lease corto (30s).
2. `now + 31s` simulado como `after` (expiry).
3. Dos threads esperan barrier, luego `reacquire_expired_lease` con owners distintos sobre la **misma** conexión pool / client (instancias repo independientes).
4. Assert estricto: no se acepta “ambos CONFLICT” ni doble acquire.

## Relación con unit / memory

- Memory (`test_memory_job_lease_fencing.py`) prueba el **contrato** sin SQL.
- SQL IT prueba **aislamiento real** (UPDLOCK/CAS UPDATE/`OUTPUT inserted.lease_fencing_token`).
- Localmente puede skippear; **CI con SQL Server + 0072** es la evidencia de merge para concurrency SQL.

## Qué no cubre (aún)

- Worker end-to-end multi-process con heartbeat real.
- Cancel / artifact / promotion races.
- Wiring de `reacquire_expired_lease` en recovery productiva.

## Corrections (2026-07-28 UTC)
- Added `test_sql_job_finalization_fencing.py` (update_finalization + cancel ack).
- SQL IT focused suite must not skip when SQL Server is available.
