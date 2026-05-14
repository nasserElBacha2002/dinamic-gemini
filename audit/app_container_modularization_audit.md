# App container modularization audit

This document tracks the **C1–C5** modularization and hardening of the v3 `AppContainer` composition root.

## Current status after C5

- **`AppContainer`** remains the public composition root: settings, cached dependencies, public `get_*` getters, one-time repository backend resolution (`_get_repository_backend_resolution`), SQL probe / client access, `_build_sql_repository_or_memory`, and **`close()`** for lifecycle cleanup.
- **Repository construction** lives in `backend/src/runtime/container/repository_builders.py` (and related C3 modules: `label_builders`, `analytics_builders`, `capture_session_builders`, `repository_backend.py`).
- **Storage / services / use-case construction** lives in `storage_builders.py`, `service_builders.py`, `use_case_builders.py`, `prompt_config_builders.py` (C4).
- **Backend modes (C2):** `MEMORY_ONLY` and `MEMORY_FALLBACK` use memory repositories for the whole container; `SQL` uses SQL repositories only — SQL constructor failures **raise**; there is **no** per-repository SQL→memory fallback after mode resolution.
- **Fallback policy (C5):** `V3_ALLOW_IN_MEMORY_FALLBACK` — if set, only `true` / `1` / `yes` allow `MEMORY_FALLBACK` when SQL is targeted but the probe fails. If **unset**, fallback is **disallowed** when `APP_ENV`, `ENVIRONMENT`, or `NODE_ENV` indicates a **production-like** runtime (`production`, `prod`, `staging`, `uat`, etc. — see `runtime_environment.py`); otherwise it defaults to **allowed** (local/dev). Policy is logged before resolution (`v3 repository_backend policy: ...`).
- **Lifecycle:** `AppContainer.close()` clears caches and best-effort calls `close` / `dispose` / `shutdown` on cached `SqlServerClient`, artifact storage, and worker launch service when present. `SqlServerClient` does not hold a pooled connection between calls (connections are per `cursor()`). `reset_app_container_for_tests()` acquires the module lock and calls `close()` on the existing container before clearing the singleton.
- **Singleton:** `get_app_container()` uses double-checked locking with `threading.Lock()`; `reset_app_container_for_tests()` uses the same lock.

> **Historical note:** Older prose that described **per-repository** SQL→memory fallback reflected **pre-C2** behavior. Since C2, fallback is **container-level** only: the backend mode is resolved once; in `SQL` mode there is no silent memory fallback per repository.

---

Phases C1–C3 (repository backend resolution, enforcement, repository builders) were completed and verified before the C4/C5 notes below.

## Phase C4 implementation note

C4 is an internal modularization phase. Non-repository construction moved out of `AppContainer`, but caching, settings ownership, backend mode resolution, and public getters remain owned by `AppContainer`.

### Builder modules added (C4)

| Module | Role |
|--------|------|
| `backend/src/runtime/container/storage_builders.py` | `build_artifact_storage`, `build_stored_artifact_reader` |
| `backend/src/runtime/container/service_builders.py` | `build_metrics_calculator`, `build_worker_launch_service`, `build_clock` |
| `backend/src/runtime/container/use_case_builders.py` | `build_recompute_consolidated_counts_use_case` |
| `backend/src/runtime/container/prompt_config_builders.py` | Supplier prompt config use-case builders |

### Dependencies extracted (C4)

- **Storage:** artifact storage (local/S3) and stored artifact reader.
- **Services:** metrics calculator, worker launch service, clock.
- **Use cases:** recompute consolidated counts; supplier prompt config use cases (with explicit return types on getters).

### Public API (C4)

- `AppContainer` public `get_*` names unchanged; `get_app_container()` / `reset_app_container_for_tests()` unchanged at the call-site level (C5 extends reset to call `close()`).

### Status (C4)

`APP_CONTAINER_C4_STORAGE_SERVICE_USE_CASE_BUILDERS_EXTRACTED` — superseded by C5 closure; see **Phase C5** and `audit/app_container_final_closure.md`.

---

## Phase C5 implementation note

### Production fallback hardening

- **`runtime_environment.py`:** `is_production_like_runtime()` reads `APP_ENV`, `ENVIRONMENT`, then `NODE_ENV` (first non-empty token wins) and compares to a fixed set aligned with `sqlserver_pytest_policy` hosted names.
- **`_v3_allow_in_memory_fallback`:** Explicit env var uses allowlist `true`/`1`/`yes` only; unset uses `not is_production_like_runtime()` so production-like hosts default to **no** memory fallback unless SQL probe succeeds or override is set.
- **Logging:** `_get_repository_backend_resolution` logs policy line (`allow_in_memory_fallback`, `production_like_runtime`, whether `V3_ALLOW_IN_MEMORY_FALLBACK` was explicitly set) before calling `resolve_repository_backend_mode`.

### Lifecycle

- **`AppContainer.close()`:** Idempotent; clears all cached repos/services/readers/resolution; best-effort optional `close`/`dispose`/`shutdown` on SQL client, artifact storage, worker launch service; warnings on failure.
- **`reset_app_container_for_tests()`:** Under `_container_lock`, calls `close()` on non-`None` container then sets global to `None`.

### Singleton / thread-safety

- **`_container_lock`:** Double-checked locking in `get_app_container()`; `reset_app_container_for_tests()` uses the same lock to avoid races with initialization.

### Tests added (C5)

- `tests/runtime/test_runtime_environment.py` — production-like detection from env vars.
- `tests/runtime/test_app_container_c5.py` — explicit/unset fallback matrix, `close` idempotency, reset invokes `close`, optional resource `shutdown` hook.

### Validation (C5)

- `cd backend && .venv/bin/python -m pytest tests/runtime/ -q` — pass
- `cd backend && .venv/bin/ruff check src/runtime/container/ src/runtime/app_container.py tests/runtime/` — pass
- `cd backend && .venv/bin/mypy src/runtime/container/ src/runtime/app_container.py` — pass

### Intentionally deferred

- Full `pytest tests/` not required for C5 DoD; prior runs showed unrelated API failures (documented in final closure report).

### Remaining risks

- Production detection relies on operators setting `APP_ENV` / `ENVIRONMENT` / `NODE_ENV`; if unset in a real production process, unset `V3_ALLOW_IN_MEMORY_FALLBACK` still defaults to **allow** fallback (developer-friendly default) — document in closure.
- `SqlServerClient` has no persistent connection to close; clearing references is the main effect.

---

## Broader test history (C4 era)

Broader run `pytest tests/ -q` had reported **3 failures** unrelated to container wiring (supplier prompt validation, aisles wiring). Re-run after C5 not required for modularization DoD.
