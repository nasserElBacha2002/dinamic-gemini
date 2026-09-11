# Auditoría: worker SQL sin repositorios de base de datos

**Veredicto inicial:** `ROOT_CAUSE_CONFIRMED`  
**Estado de implementación:** `IMPLEMENTED_WITH_LIMITATIONS`

## Causa raíz confirmada

El mensaje

```text
SQL worker mode configured but DB repositories are unavailable; cannot claim queued jobs
```

**no significaba que SQL Server estuviera caído.** El runner de migraciones y `GET /ready` podían estar sanos porque el backend v3 (`AppContainer` → `SqlJobRepository` sobre `inventory_jobs`) sí estaba inicializado.

`claim_next_job` (introducido en `ed37d78f`, 2026-03-20) trata `SQLSERVER_ENABLED=true` + connection string como “modo SQL”. El claim preferido es v3 (`get_job_repo().claim_next_queued_job()`). Cuando ese claim **tiene éxito y no hay jobs** (`None`), el código **caía al puente legacy** `job_store._db_repos()`.

Desde `15536667` (2026-04-16), `_db_repos()` devuelve `None` si `LEGACY_STAGE8_SQL_BRIDGE_DISABLED=true`, o si falla la construcción de `JobsRepository` (tablas `jobs` / `pallet_results` / `job_events`). Entonces `db_claim_configured` seguía true y **cada poll idle** (1 s) emitía ERROR.

Eso encaja con la evidencia de DEV:

| Observación | Interpretación |
|-------------|----------------|
| Contenedor healthy, `GET /ready` `{"ok": true}` | Schema + backend v3 SQL OK; `/ready` **no** miraba el worker |
| `db_migrate.py status` OK | ODBC / SQL Server alcanzable |
| Warning repetido | Poll idle + `_db_repos() is None` + SQL mode |
| Jobs v3 | El worker **sí podía** reclamar `inventory_jobs` cuando había cola; el error era en idle |

No hay dos `JobStore` de clase: el módulo `job_store` es funcional. El worker embebido y el API comparten `get_app_container().get_job_repo()`. El fallo era de **contrato de claim**, no de DI duplicada.

## Flujo reconstruido

```text
EMBEDDED_WORKER_ENABLED / SQLSERVER_ENABLED
→ FastAPI startup (schema guard)
→ get_app_container()  (SQL probe → SqlJobRepository)
→ thread daemon worker_loop
→ claim_next_job cada ~1s
    → v3 get_job_repo().claim_next_queued_job()
    → si None: _db_repos()  [legacy Stage-8]
    → si None y sql_mode: ERROR  ← aquí
→ /health liveness (ok siempre true)
→ /ready: schema + repository backend + (antes) nada del worker
```

## Archivos y líneas (antes)

- Warning: `backend/src/jobs/job_store.py` ~233–238 (`ed37d78f`, log ERROR en `43f3e5e4`)
- `_db_repos()` None si puente off: mismas ~32–48 (`15536667`)
- Worker poll: `backend/src/jobs/worker.py` `worker_loop`
- Startup thread: `backend/src/api/server.py` `start_worker` (después del container)
- `/ready` no consultaba worker: `backend/src/api/server.py` `ready()`

## Impacto sobre jobs

- Cola v3 vacía: spam de ERROR; no hay pérdida de jobs.
- Cola v3 con `QUEUED`: el claim v3 ocurría **antes** del warning; procesamiento posible.
- Si `get_job_repo()` fallaba de verdad: jobs v3 quedan `QUEUED` sin claim; `/ready` seguía 200. Ese caso ahora marca `JOB_WORKER_UNAVAILABLE`.
- No hay otro worker en Compose DEV (solo `api` embebido). Leases/CAS siguen en `SqlJobRepository`.

## Hipótesis descartadas

| Hipótesis | Evidencia en contra |
|-----------|---------------------|
| SQL Server caído | Migraciones y schema guard OK |
| AppContainer en memoria | `/ready` ok + SQL enabled en DEV implica backend SQL healthy |
| Worker deshabilitado | `EMBEDDED_WORKER_ENABLED=true` y thread arrancaba |
| Falta de archivos de migración en la imagen | `db_migrate.py status` compatible |
| Store distinto API vs worker | Mismo `get_job_repo()` de `v3_deps` |

## Solución elegida

1. **Idle v3 en modo SQL es éxito.** Si `claim_next_queued_job` existe y devuelve `None`, no se exige `_db_repos()`. El puente Stage-8 sigue drenando jobs legacy **solo si está armado**.
2. **ERROR solo si modo SQL y no hay path de claim** (v3 no claimable y legacy `None`). Log `job_worker_unavailable reason=...` **una vez**, luego cada 30 s. Recuperación: `job_worker_recovered downtime_seconds=...`.
3. **`/ready`** cuando `EMBEDDED_WORKER_ENABLED=true`: 503 `JOB_WORKER_UNAVAILABLE` si el thread no arrancó, murió, o el claim path está unavailable. Cola vacía = healthy. Si el worker es dedicado (`EMBEDDED_WORKER_ENABLED=false`), no se exige el thread local.
4. **Startup:** se configura el runtime **después** del container; se valida `get_job_repo()` + `claim_next_queued_job`. Si el backend resuelto es SQL y el repo no se puede construir, el startup **falla** (estructural). Un solo thread; shutdown pide stop y `join(5s)`.
5. No se desactiva el worker ni se fuerza memoria.

Preferencia aplicada: fallo de **startup** si SQL backend resuelto no puede construir el JobRepository; fallo de **`/ready`** si el loop muere o el claim path queda unavailable (operativo / transitorio).
