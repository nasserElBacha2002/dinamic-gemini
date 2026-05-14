# App container modularization — final closure report (C5)

## 1. Executive summary

Phases **C0–C5** complete the v3 `AppContainer` track: repository backend resolution (C1/C2), builder extraction (C3/C4), and **C5** production fallback hardening, lifecycle `close()`, test reset wiring, singleton locking, and documentation alignment.

**Final status:** `APP_CONTAINER_FINAL_CLOSED_WITH_OBSERVATIONS` — production safety improved and contracts documented; a residual risk remains if production hosts omit both production-like env markers and explicit `V3_ALLOW_IN_MEMORY_FALLBACK=false` (see section 7).

## 2. Final architecture

| Concern | Location |
|--------|----------|
| Settings ownership | `AppContainer._settings` |
| Cached singletons | `AppContainer` private `_…` fields |
| Public accessors | `AppContainer.get_*` (names unchanged) |
| Repository backend resolution | `AppContainer._get_repository_backend_resolution` + `container/repository_backend.resolve_repository_backend_mode` |
| SQL probe / client | `AppContainer._probe_sql_for_repository_backend`, `_get_v3_sql_client` |
| Repository SQL vs memory construction | `container/repository_builders.py` (+ label/analytics/capture builders) via `_build_sql_repository_or_memory` |
| Artifact storage & reader | `container/storage_builders.py` |
| Metrics, worker launch, clock | `container/service_builders.py` |
| Recompute + prompt-config use cases | `use_case_builders.py`, `prompt_config_builders.py` |
| Production-like runtime hint | `container/runtime_environment.is_production_like_runtime` |
| Process singleton | `get_app_container` / `reset_app_container_for_tests` in `app_container.py` |

## 3. Backend mode contract

```text
MEMORY_ONLY:
  SQL is not targeted by settings (disabled or no effective connection string).
  All repositories use memory. SQL probe is not run.

MEMORY_FALLBACK:
  SQL was targeted but the initial probe failed and in-memory fallback was allowed
  by policy (explicit V3_ALLOW_IN_MEMORY_FALLBACK or non-production default).
  All repositories use memory for this process/container.

SQL:
  SQL probe succeeded.
  All repositories use SQL.
  SQL repository construction failures raise.
  No fallback to memory occurs in SQL mode after resolution.
```

## 4. Production fallback policy

| `V3_ALLOW_IN_MEMORY_FALLBACK` | Effect |
|--------------------------------|--------|
| Set to `true` / `1` / `yes` | Allow `MEMORY_FALLBACK` when SQL is targeted and probe fails. |
| Set to anything else (e.g. `false`, `0`, `no`) | Disallow fallback; probe failure propagates. |
| **Unset** | If `is_production_like_runtime()` → **disallow** fallback. If not production-like → **allow** fallback (local/dev default). |

**Production-like runtime** is determined only from environment variables (no `AppSettings.environment` field today): `APP_ENV`, `ENVIRONMENT`, then `NODE_ENV` — first non-empty value is normalized and matched against tokens such as `production`, `prod`, `staging`, `uat`, `live`, `demo`, etc. (see `backend/src/runtime/container/runtime_environment.py`).

**Operational implication:** Hosted production should set `APP_ENV=production` (or equivalent) **or** set `V3_ALLOW_IN_MEMORY_FALLBACK` explicitly. If neither production-like env nor explicit disallow is present, unset fallback still **allows** memory fallback (developer default).

## 5. Lifecycle contract

- **`AppContainer.close()`** exists. It clears all cached dependencies and resolution state; it best-effort invokes `close`, `dispose`, or `shutdown` on the cached `SqlServerClient`, artifact storage, and worker launch service **if** those callables exist.
- **`SqlServerClient`** does not keep a long-lived ODBC connection; each `cursor()` opens and closes a connection. Clearing the cached client reference is the main lifecycle effect.
- **`reset_app_container_for_tests()`** acquires `_container_lock`, calls `close()` on the existing container when present, then sets the global container to `None`.
- **Limitations:** Memory repositories and most adapters do not expose cleanup hooks; no pool teardown beyond clearing references.

## 6. Validation results

Commands run (2026-05-13, backend venv):

```bash
cd backend
.venv/bin/python -m pytest tests/runtime/ -q
```

**Result:** pass (44 tests in `tests/runtime/` after C5 additions).

```bash
.venv/bin/ruff check src/runtime/container/ src/runtime/app_container.py tests/runtime/
```

**Result:** pass.

```bash
.venv/bin/mypy src/runtime/container/ src/runtime/app_container.py
```

**Result:** pass.

**Full `pytest tests/`:** Not re-run as part of C5 closure (prior C4 note: unrelated failures in API tests). Re-run in CI or locally when validating unrelated areas.

## 7. Remaining risks

- **Env detection gap:** If a production deployment does not set `APP_ENV` / `ENVIRONMENT` / `NODE_ENV` to a production-like value, the **unset** `V3_ALLOW_IN_MEMORY_FALLBACK` default still allows memory fallback on SQL probe failure.
- **Global singleton:** One process-wide container; lock serializes init/reset only — long-held user code on container is unchanged.
- **Historical audit sections:** Older notes may describe pre-C2 behavior; the modularization audit now includes a **historical** callout at the top.
- **AppContainer scope:** Large getter surface intentionally retained for backward compatibility; further splits would be a new track.

## 8. Final status

```text
APP_CONTAINER_FINAL_CLOSED_WITH_OBSERVATIONS
```
