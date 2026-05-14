# App container modularization audit

Phases C1–C3 (repository backend resolution, enforcement, repository builders) were completed and verified before this document was introduced.

## Phase C4 implementation note

C4 is an internal modularization phase. Non-repository construction moved out of `AppContainer`, but caching, settings ownership, backend mode resolution, and public getters remain owned by `AppContainer`.

### Builder modules added

| Module | Role |
|--------|------|
| `backend/src/runtime/container/storage_builders.py` | `build_artifact_storage`, `build_stored_artifact_reader` |
| `backend/src/runtime/container/service_builders.py` | `build_metrics_calculator`, `build_worker_launch_service`, `build_clock` |
| `backend/src/runtime/container/use_case_builders.py` | `build_recompute_consolidated_counts_use_case` |
| `backend/src/runtime/container/prompt_config_builders.py` | Supplier prompt config use-case builders (list, create version, get active, activate version, get by id) |

### Dependencies extracted

- **Storage:** artifact storage (local/S3 branching, logging, directory creation) and stored artifact reader.
- **Services:** inventory metrics calculator, on-demand worker launch service, UTC clock (still a fresh instance per `get_clock()` call; not cached in the container).
- **Use cases:** `RecomputeConsolidatedCountsUseCase` construction (still **not** cached — new instance per `get_recompute_consolidated_counts_use_case()` as before).
- **Prompt config use cases:** all five supplier prompt config getters delegate to `prompt_config_builders`; getters gained explicit return types; behavior remains uncached (new instance per call).

### Intentionally left in `AppContainer`

- `AppSettings` / `_settings`
- All cached repository and infrastructure fields (`_artifact_storage`, `_stored_artifact_reader`, `_metrics_calculator`, `_worker_launch_service`, etc.)
- Public `get_*` method names and signatures (unchanged API surface)
- `_get_repository_backend_resolution`, `_build_sql_repository_or_memory`, `_get_v3_sql_client`, `_probe_sql_for_repository_backend`, `V3_ALLOW_IN_MEMORY_FALLBACK` handling
- Lazy call order via getters passing dependencies into builders

### Public API

- `AppContainer` public method names are unchanged.
- `get_app_container()` and `reset_app_container_for_tests()` are unchanged.

### Repository backend semantics (C2/C3)

Unchanged: `MEMORY_ONLY` / `MEMORY_FALLBACK` → memory repositories; `SQL` → SQL repositories or raise; no per-repository SQL→memory fallback after mode resolution.

### Tests and validation

Commands run:

- `cd backend && .venv/bin/python -m pytest tests/runtime/ -q` — pass
- `cd backend && .venv/bin/ruff check src/runtime/container/ src/runtime/app_container.py tests/runtime/` — pass
- `cd backend && .venv/bin/mypy src/runtime/container/ src/runtime/app_container.py` — pass

Broader run `pytest tests/ -q` reported **3 failures** that do not point at container wiring (e.g. supplier prompt API expecting 201 but receiving 400 `SUPPLIER_PROMPT_CONFIG_INVALID_MODEL`; aisles wiring test on processing provider keys). Treat as **pre-existing or environment-dependent** unless reproduced on a clean baseline; C4 changes do not alter those code paths beyond delegating the same use-case constructors.

### Remaining risks / future phases

- Further extraction (e.g. analytics/capture builders already exist from C3) or splitting oversized builder files if more use cases move to the container.
- Optional: cache `get_clock()` or prompt use cases only if product explicitly requires it (currently preserves prior semantics).

### Status

`APP_CONTAINER_C4_STORAGE_SERVICE_USE_CASE_BUILDERS_EXTRACTED`
