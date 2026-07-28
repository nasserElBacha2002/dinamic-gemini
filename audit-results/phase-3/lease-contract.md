# Phase 3 — Lease contract

Contrato de dominio y persistencia para **job lease fencing** (`backend/src/domain/jobs/lease.py` + `JobRepository` port).

## JobLease fields

| Campo | Tipo | Semántica |
|---|---|---|
| `job_id` | `str` | Inventory job id |
| `owner_id` | `str` | Worker token; **igual** a `Job.claim_owner_id` |
| `fencing_token` | `int` | Token monotónico asignado por persistence |
| `acquired_at` | `datetime` | Momento de acquire / reacquire |
| `expires_at` | `datetime` | Expiración; renew extiende este valor |

`JobLease` es `@dataclass(frozen=True)`. Callers **nunca** inventan `fencing_token`.

## Persistencia asociada (`inventory_jobs`)

| Columna | Notas |
|---|---|
| `claim_owner_id` | Owner del lease (reutilizado; no hay `lease_owner_id`) |
| `lease_fencing_token` | `BIGINT NOT NULL`, default `0` |
| `lease_expires_at` | `DATETIME2 NULL` |
| `lease_acquired_at` | `DATETIME2 NULL` |

## LeaseWriteOutcome

Resultado de writes condicionados al lease (`merge_result_json_if_leased`, `complete_if_leased`, `fail_if_leased`, `assert_lease`):

| Valor | Significado |
|---|---|
| `applied` | CAS ganó; mutación aplicada (o assert OK) |
| `lease_lost` | Owner/token mismatch o lease expirado |
| `job_terminal` | Job ya terminal |
| `not_found` | Job inexistente |
| `invalid_state` | Status no leasable / CAS miss no clasificado |

Wrapper: `LeaseWriteResult(outcome, reason)` con `.applied`.

## LeaseRenewalOutcome

Resultado de `renew_lease` / `touch_heartbeat_if_leased`:

| Valor | Significado |
|---|---|
| `renewed` | Expiry + heartbeat extendidos; token **sin** cambio |
| `lease_lost` | Otro owner / otro fencing token |
| `expired` | Mismo owner+token pero `lease_expires_at < now` |
| `job_terminal` | Job terminal |
| `not_found` | Job ausente |
| `invalid_state` | Status no leasable / unclassified |

Wrapper: `LeaseRenewalResult(outcome, lease, reason)` con `.renewed`. On success, `lease` refleja el nuevo `expires_at`.

## JobLeaseLostError

Excepción cooperativa: este worker ya no posee el lease.

- **No** implica marcar el job `FAILED`.
- Lleva contexto opcional: `job_id`, `owner_id`, `fencing_token`, `reason`.
- Worker / finalization atrapan y hacen halt / `runtime_abort`.

## CAS conditions (writes / renew)

Una operación lease-conditioned aplica solo si **todas** se cumplen:

1. Job existe.
2. `status ∈ {running, cancel_requested}` (`LEASE_ACTIVE_STATUSES`).
3. `claim_owner_id == lease.owner_id` (ambos non-empty strip-equal).
4. `lease_fencing_token == lease.fencing_token`.
5. `lease_expires_at` is null **or** `lease_expires_at >= now` (renew SQL uses `>= now`; expired → miss).

Helpers compartidos: `job_lease_helpers.lease_is_currently_valid` / `classify_lease_*_after_cas_miss`.

## Renew vs reacquire

| | `renew_lease` | `reacquire_expired_lease` |
|---|---|---|
| Quién | Mismo `owner_id` + mismo `fencing_token` | Nuevo `new_owner_id` |
| Precondición | Lease **aún válido** (no expirado) | `status=running` y `lease_expires_at < now` |
| Token | **No** incrementa | **`+1`** (fencing) |
| Owner | Sin cambio | Reemplaza `claim_owner_id` |
| Uso | Heartbeat del worker activo | Steal / recovery controlada (repo + tests; prod wiring pendiente) |
| Log | `job_lease_renewed` / `job_lease_lost` | `job_lease_reacquired` |

## Claim acquire

`try_claim_starting_to_running(..., lease_duration_seconds)` en acquire exitoso:

- Phase 1 CAS STARTING→RUNNING + aisle PROCESSING.
- Asigna owner, `fencing_token` (increment), `lease_acquired_at`, `lease_expires_at = now + duration`.
- Devuelve `JobClaimResult.lease: JobLease | None`.

## Settings

- `JOB_LEASE_DURATION_SEC` (default 60) — grant / extension.
- `JOB_LEASE_HEARTBEAT_INTERVAL_SEC` (default 15) — loop interval.
- `JOB_LEASE_RENEWAL_SAFETY_MARGIN_SEC` (default 20) — documentado en settings; **aún no** usado por la lógica de urgencia del heartbeat.

## Corrections (2026-07-28 UTC)
- Null expiry / token 0 / empty owner → `lease_not_initialized`.
- Finalization writes allowed on SUCCEEDED for completing owner/token.
- Ports: lease ops are `@abstractmethod` incl. tracker/cancel.
