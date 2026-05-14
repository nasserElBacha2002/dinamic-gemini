# AppContainer modularization — read-only technical audit

**Scope:** `backend/src/runtime/app_container.py`, related wiring (`v3_deps.py`, `api/dependencies.py`), `SqlServerClient`, settings affecting SQL vs memory.  
**Out of scope (this document):** No production code changes; no new runtime dependencies; no API or worker behavior changes.  
**Date:** 2026-05-13  

---

## 1. Executive summary

`AppContainer` is the documented **composition root** for v3: it lazily constructs repositories (SQL vs in-memory), artifact storage, metrics service, stored artifact reader, worker launch service, and several supplier prompt-config use cases. Construction is **centralized and repetitive**, with a shared helper `_build_sql_repository_or_memory` and per-repository nested `_sql` / `_memory` factories.

**Main risks:** (1) **`V3_ALLOW_IN_MEMORY_FALLBACK` defaults to enabled** (`"true"` when unset), so SQL initialization failures can **silently** yield in-memory repositories while other getters may still use SQL after a successful `SqlServerClient` probe — a **per-repository** fallback can produce **mixed backends** in edge cases. (2) **No process-level lock** on `get_app_container()`’s global singleton (low risk under typical single-process FastAPI / one worker per process). (3) **No explicit shutdown** for a cached `SqlServerClient` (acceptable today because `SqlServerClient` opens connections per `cursor()` and closes them in `finally`). (4) **Several use-case getters lack return type annotations**, weakening static guarantees.

**Recommendation:** **`APP_CONTAINER_REFACTOR_RECOMMENDED`** — the container is coherent and testable, but **modularization + a single resolved repository backend mode** would reduce operational risk and maintenance load without changing public getters in early phases.

---

## 2. Current architecture map

| Layer | Role |
|--------|------|
| **API** | `dependencies.py` documents fallback semantics; delegates to `get_app_container()` / `v3_deps`. |
| **Runtime** | `app_container.py` owns lazy singleton graph; `v3_deps.py` exposes thin getters. |
| **Infrastructure** | SQL and memory repository implementations imported **inside** getters (deferred import). |
| **Application** | Ports (`*Repository`, `ArtifactStorage`, etc.); use cases built from container getters. |

`AppContainer.__init__` only stores `AppSettings` and `None` placeholders for cached instances (`app_container.py` roughly L76–L102).

---

## 3. Current flow map (dependency construction)

1. **`get_app_container()`** (L57–L64): global `_container`; lazy `AppContainer(load_settings())` on first access.
2. **`_v3_db_enabled()`** (L113–L117): `settings.sqlserver_enabled` **and** non-empty `sqlserver_effective_connection_string`.
3. **`_v3_allow_in_memory_fallback()`** (L108–L111): env `V3_ALLOW_IN_MEMORY_FALLBACK`, default **`"true"`** if unset.
4. **`_get_v3_sql_client()`** (L119–L126): lazy singleton `SqlServerClient`; **`SELECT 1`** via `cursor()` before cache assignment.
5. **`_build_sql_repository_or_memory(...)`** (L128–L157): if DB disabled → `build_memory()`; else try `build_sql(_get_v3_sql_client())` on **any** exception → log; if fallback allowed → `build_memory()`, else re-raise.
6. **Per-port getters** (`get_*_repo`): check instance cache → delegate to `_build_sql_repository_or_memory` with local `_sql` / `_memory` closures importing concrete classes.
7. **Non-repository getters:** `get_metrics_calculator` (caches service using repos), `get_artifact_storage` (S3 vs local), `get_stored_artifact_reader`, `get_worker_launch_service`, `get_recompute_consolidated_counts_use_case` (always new instance), supplier prompt use-case getters (always new instances), `get_clock` (always new `UtcClock`).

---

## 4. Plan/spec requirements extracted (from audit brief)

| Requirement | Notes |
|-------------|--------|
| Map responsibilities and dependency categories | Below §5. |
| Identify infra built directly in container | Yes — SQL client, storage, readers, services, use cases. |
| Repository backend selection | `_v3_db_enabled` + per-repo `_build_sql_repository_or_memory`. |
| SQL vs memory consistency | Desired: **single mode per process**; current: **per-getter try/except**. |
| Lifecycle / singleton / typing / god-object | Addressed in §6–§8. |
| Modularization proposal | §9. |
| Phased roadmap | §11. |
| No production code in this phase | This file only. |

---

## 5. Responsibility map (grouped)

### 5.1 Core inventory / aisle / job / assets

| Getter | Backend pattern |
|--------|-----------------|
| `get_inventory_repo` | `_build_sql_repository_or_memory` (L159–L183) |
| `get_aisle_repo` | L235–L257 |
| `get_job_repo` | L259–L279 |
| `get_source_asset_repo` | L281–L305 |

### 5.2 Client / supplier

| Getter | Backend pattern |
|--------|-----------------|
| `get_client_repo` | L185–L207 |
| `get_client_supplier_repo` | L209–L233 |
| `get_supplier_reference_image_repo` | L307–L331 |
| `get_supplier_prompt_config_repo` | L333–L357 |

### 5.3 Positions / products / evidence / review

| Getter | Backend pattern |
|--------|-----------------|
| `get_position_repo` | L359–L383 |
| `get_product_record_repo` | L385–L409 |
| `get_evidence_repo` | L411–L435 |
| `get_review_action_repo` | L437–L461 |

### 5.4 Label / final-count domain

| Getter | Backend pattern |
|--------|-----------------|
| `get_raw_label_repo` | L544–L568 |
| `get_normalized_label_repo` | L570–L594 |
| `get_final_count_repo` | L596–L620 |

### 5.5 Analytics

| Getter | Notes |
|--------|--------|
| `get_analytics_repo` | L622–L650; **memory** branch injects **other repos** via `self.get_*` (L635–L641) — cross-repo coupling. |

### 5.6 Capture sessions

| Getter | Notes |
|--------|--------|
| `get_capture_session_repo` | L652–L675 |
| `get_capture_session_item_repo` | L677–L700 |
| `get_capture_session_group_repo` | L702–L725; memory path: `MemoryCaptureSessionGroupRepository(self.get_capture_session_item_repo())` — **order-dependent** if backends mixed. |
| `get_capture_session_confirm_repo` | L727–L750 |

### 5.7 Storage / artifacts

| Getter | Notes |
|--------|--------|
| `get_artifact_storage` | L478–L520; **S3 vs local** branch; raises if S3 without bucket. |
| `get_stored_artifact_reader` | L522–L532; uses `get_job_repo()` + `get_artifact_storage()`. |

### 5.8 Services / worker

| Getter | Notes |
|--------|--------|
| `get_metrics_calculator` | L463–L472; `InventoryMetricsService` with aisle + position repos. |
| `get_worker_launch_service` | L534–L542; `OnDemandWorkerLaunchService`. |

### 5.9 SQL client / configuration

| Member / method | Notes |
|-----------------|--------|
| `_v3_sql_client` | Cached after successful probe (L119–L126). |
| `_v3_db_enabled` | Settings gate (L113–L117). |
| `_v3_allow_in_memory_fallback` | Env gate (L108–L111). |

### 5.10 Use cases (application layer wired in container)

| Method | Notes |
|--------|--------|
| `get_recompute_consolidated_counts_use_case` | L752–L765; builds domain services + use case **each call** (no instance cache). |
| `get_list_supplier_prompt_configs_use_case` | L767–L777 |
| `get_create_supplier_prompt_config_version_use_case` | L779–L790 |
| `get_get_active_supplier_prompt_config_use_case` | L792–L802 |
| `get_activate_supplier_prompt_config_version_use_case` | L804–L813 |
| `get_get_supplier_prompt_config_use_case` | L815–L824 |

### 5.11 Singleton / global lifecycle

| Symbol | Notes |
|--------|--------|
| `_container` | Module global (L54); `get_app_container` / `reset_app_container_for_tests` (L57–L70). |

### 5.12 Miscellaneous

| Method | Notes |
|--------|--------|
| `get_clock` | L474–L477; **new `UtcClock` per call** — not cached (acceptable if stateless). |

---

## 6. Gap analysis (current vs desired “single backend mode”)

| Topic | Current | Gap |
|--------|---------|-----|
| Backend resolution | Per-repository `_build_sql_repository_or_memory` | No single **process-wide** “we are in SQL mode” vs “memory mode” decision logged once. |
| Fallback on SQL error | Per-getter `except` | One repo can fall back while `_v3_sql_client` remains set for others → **mixed** risk (§7b). |
| Production safety | `V3_ALLOW_IN_MEMORY_FALLBACK` **true** by default | Production can silently run on memory after partial failure unless env is tightened (`dependencies.py` L7–L10 already documents setting `false`). |
| Shutdown | No `AppContainer.close()` | `SqlServerClient` does not hold long-lived connections (see §7c); gap is **observability / future pooling**, not an immediate leak. |

---

## 7. Risk analysis (audit questions)

### 7a) In-memory fallback default

- **Code:** `_v3_allow_in_memory_fallback` uses `(os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") or "true")` → default **enabled** (`app_container.py` L109–L111).
- **Production safety:** **Not ideal as default for production-like deployments.** If SQL is misconfigured or temporarily down, the API may **appear healthy** while persisting to **ephemeral** stores — data loss and cross-request inconsistency vs operators’ expectations.
- **Mitigation (documented elsewhere):** `dependencies.py` L7–L10 recommends `false` in production-like environments.

### 7b) Mixed backend state

- **Can SQL and memory coexist?** **Yes, in edge cases:**
  1. `_v3_db_enabled()` is **true**; `_get_v3_sql_client()` **succeeds** and caches `SqlServerClient`.
  2. `build_sql(client)` for **repository A** raises (e.g., import error, constructor bug, or rare driver issue after probe).
  3. Handler catches, logs, returns **memory** for A **without** clearing `_v3_sql_client`.
  4. **Repository B** is later built with the **same cached client** → **SQL** for B.
- **Concrete coupling:** `MemoryAnalyticsRepository(..., self.get_job_repo(), ...)` (L635–L641) assumes peer repositories; if analytics fell back to memory but jobs stayed SQL, **analytics aggregates can diverge** from persisted job truth.
- **Capture sessions:** `MemoryCaptureSessionGroupRepository(self.get_capture_session_item_repo())` (L717–L718) ties group memory constructor to item repo instance — **consistent if both paths agree**; **risk if item SQL and group memory** due to asymmetric failures.

### 7c) SQL client lifecycle

- **`SqlServerClient`:** `cursor()` opens `pyodbc.connect`, commits/rolls back, **closes connection in `finally`** (`sqlserver.py` L37–L60). The cached client is a **lightweight factory** over a connection string, not a connection pool.
- **Cached in container:** `_v3_sql_client` (L78, L119–L126). **No `close()`** on `SqlServerClient` — **currently low impact** because no persistent connection is kept open on the instance.
- **API vs workers:** Each process has its own `get_app_container()` singleton; workers inherit the same pattern — **no shared cross-process client**.

### 7d) Global singleton

- **Implementation:** `global _container` without threading lock (`app_container.py` L57–L64).
- **Typical deployment:** Uvicorn **workers are processes** → one container per worker; **async request path** is single-threaded per process → **low practical risk**.
- **Theoretical risk:** Multi-threaded WSGI-style or concurrent first initialization could race on `_container = None` check (rare in current stack).

### 7e) Type safety

- **Missing return annotations** (should be added in a later phase):
  - `get_list_supplier_prompt_configs_use_case` (L767)
  - `get_create_supplier_prompt_config_version_use_case` (L779)
  - `get_get_active_supplier_prompt_config_use_case` (L792)
  - `get_activate_supplier_prompt_config_version_use_case` (L804)
  - `get_get_supplier_prompt_config_use_case` (L815)
- **Well-typed:** Most `get_*_repo` and service getters return port/service types explicitly.

### 7f) File size / “God container”

- **~826 lines**, many near-identical repository blocks — **high boilerplate**, **clear extraction target** (repository builder module) without changing public API.
- **Use-case getters** mix **construction** with **imports** — candidates for `use_case_builders.py`-style module.

### 7g) Circular import / deferred imports

- **Pattern:** `from src.infrastructure.repositories...` inside `_sql` / `_memory` closures **defers** heavy infrastructure imports until first use.
- **Why it helps:** Avoids import cycles if concrete repos or SQL adapters import modules that eventually import `app_container` or `config` during package initialization.
- **Risk:** Low; cost is slightly slower first call and less obvious dependency graph (mitigated by keeping builders in dedicated modules with explicit imports in a refactor).

---

## 8. Affected files and modules (read-only inventory)

| Path | Relationship |
|------|----------------|
| `backend/src/runtime/app_container.py` | Composition root (this audit). |
| `backend/src/runtime/v3_deps.py` | Delegates to `get_app_container()` getters. |
| `backend/src/api/dependencies.py` | Documents fallback; uses container for artifact storage etc. |
| `backend/src/database/sqlserver.py` | Connection-per-cursor semantics. |
| `backend/src/config.py` / `env_settings/grouped_settings.py` | `sqlserver_enabled` default **true** when `SQLSERVER_ENABLED` unset (`grouped_settings.py` L884–L888). |
| `backend/tests/runtime/test_app_container.py` | Singleton / wiring tests. |

---

## 9. Proposed modular architecture (incremental)

**Goal:** Keep **`AppContainer` public API** (`get_*` methods, `settings`, `get_app_container`) **stable**; move **internal** construction to focused modules.

### 9.1 Suggested package layout (under `backend/src/runtime/`)

```
runtime/
  app_container.py          # Thin orchestrator: settings, cache fields, delegates to builders
  container/
    __init__.py
    repository_backend.py   # RepositoryBackendMode enum + resolver (SQL vs MEMORY vs FAIL)
    repository_builders.py  # Functions: build_inventory_repo(container_state, ...) — pure where possible
    storage_builders.py     # artifact storage + stored artifact reader
    service_builders.py     # metrics calculator, worker launch
    use_case_builders.py    # recompute + supplier prompt use cases
    capture_builders.py     # optional: capture session quartet
    lifecycle.py            # optional: reset hooks, future close()/dispose
```

**Alternative:** Keep a single `container_wiring.py` if splitting feels too granular — prefer **2–4 files** over many micro-files.

### 9.2 Backend selection strategy (design)

**Enum / value object (conceptual):**

```text
RepositoryBackendMode:
  MEMORY_ONLY          # sqlserver disabled or no effective connection string
  SQL                  # SQL selected and client probe succeeded
  MEMORY_FALLBACK      # only if explicitly allowed and probe/build failed (deprecated path for prod)
  FAILED               # SQL required but unavailable — fail fast
```

**Resolver responsibilities (single call at container init or first repo access):**

1. Read `settings.sqlserver_enabled` and `sqlserver_effective_connection_string` (same semantics as `_v3_db_enabled`).
2. If disabled → `MEMORY_ONLY`, log once.
3. If enabled → attempt `_probe_sql()` once (equivalent to current `SELECT 1`); on success → `SQL` and cache `SqlServerClient`.
4. On failure → if `V3_ALLOW_IN_MEMORY_FALLBACK` → `MEMORY_FALLBACK` **for all repositories** (not per-repo), log **critical** warning with exception; else raise.

**Backward compatibility (phase 1):**

- Log resolved mode at **INFO** (or **WARNING** for fallback).
- Optionally keep per-repo try/except **behind** the same resolved mode flag so behavior is **identical** until a flag `V3_REPOSITORY_BACKEND_STRICT=1` enables fail-fast batch semantics.

**Production hardening (later phase):**

- Default `V3_ALLOW_IN_MEMORY_FALLBACK` to **false** only after release notes + tests (breaking for devs who rely on silent fallback).

### 9.3 Logging

- Single log line: `v3 repository backend resolved: mode=%s sqlserver_enabled=%s fallback_env=%s`.
- On any fallback: include exception type and **first** stack cause summary.

---

## 10. Migration strategy

- **No DB migrations** required — behavioral / structural Python only.
- **Operational:** communicate env var expectations (`V3_ALLOW_IN_MEMORY_FALLBACK`, `SQLSERVER_ENABLED`) when changing defaults.

---

## 11. Recommended implementation phases

| Phase | Content | DoD |
|-------|---------|-----|
| **C0** | Read-only audit (this document) | Stakeholders agree on risks and direction. |
| **C1** | Type annotations + docstrings on use-case getters; optional `AppContainer.shutdown()` no-op or delegating to future `SqlServerClient.close()` if added | `mypy` / ruff clean for touched signatures. |
| **C2** | Introduce `RepositoryBackendMode` + resolver module; **log** resolved mode; **no behavior change** initially | Unit tests: same env → same mode; logs asserted in caplog. |
| **C3** | Extract `_build_sql_repository_or_memory` and per-repo factories to `repository_builders.py`; `AppContainer` delegates | Container line count drops; **zero** public getter renames. |
| **C4** | Extract `storage_builders`, `service_builders`, `use_case_builders` | Same public API; import graph unchanged or simpler. |
| **C5** | **Strict single-mode:** on SQL probe failure, either all-memory or all-fail per env; consider default `V3_ALLOW_IN_MEMORY_FALLBACK=false` for `ENV=production` | Integration tests; runbook update. |

Rollback: revert builder modules; keep `app_container.py` on main as sole wiring until confidence is high.

---

## 12. Backward compatibility constraints

- **Preserve:** `get_app_container()`, `reset_app_container_for_tests()`, all `get_*` method **names** and **return port types**.
- **Preserve:** Current fallback **semantics** until an explicit phase flips defaults (avoid surprise prod outages).
- **Avoid:** Dynamic DI registries, string-based service location, or magic autowiring that hides dependencies from grep.

---

## 13. Recommended tests (future phases)

| Test | Intent |
|------|--------|
| Resolver unit tests | Given env/settings matrix → expected `RepositoryBackendMode`. |
| “No mixed backends” integration | Simulate `build_sql` failure for first repo; assert **either** all subsequent repos use memory **or** container raises (per chosen strict mode). |
| Singleton / reset | Existing `test_app_container.py` patterns; add thread-stress optional. |
| Lifecycle | If `close()` added: call twice idempotent. |
| Artifact storage | Existing `test_artifact_storage_single_instance_across_api_v3deps_container` — keep passing. |

---

## 14. Open questions

1. **Operational default:** Should `SQLSERVER_ENABLED` default remain `true` when many local devs run without SQL? (Today: `grouped_settings.py` L884–L888.)
2. **Strict fallback scope:** Should **artifact storage** ever participate in the same “backend mode” story, or remain independent (currently independent — correct)?
3. **Use-case caching:** Should supplier prompt use cases be **singletons** like repos, or intentionally fresh instances (current behavior — clarify for performance / test isolation)?

---

## 15. Final recommendation label

**`APP_CONTAINER_REFACTOR_RECOMMENDED`**

Rationale: the design is **functional and documented**, but **default in-memory fallback**, **per-repository exception handling**, and **826-line centralized wiring** create **avoidable operational and maintainability risk**. An incremental extractor + **single resolved backend mode** addresses the issues without a big-bang rewrite.

---

## 16. Appendix — concrete code references

Singleton composition root and reset hook:

```54:70:backend/src/runtime/app_container.py
_container: AppContainer | None = None


def get_app_container() -> AppContainer:
    """Return the process-wide application container (lazy-initialized)."""
    global _container
    if _container is None:
        from src.config import load_settings

        _container = AppContainer(load_settings())
    return _container


def reset_app_container_for_tests() -> None:
    """Drop the cached container (unit tests / isolated wiring checks)."""
    global _container
    _container = None
```

Fallback default, DB gate, SQL client probe, and **per-repository** SQL vs memory branch (note: `build_sql` failure does **not** clear `_v3_sql_client`):

```108:157:backend/src/runtime/app_container.py
    @staticmethod
    def _v3_allow_in_memory_fallback() -> bool:
        raw = (os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") or "true").strip().lower()
        return raw in ("true", "1", "yes")

    def _v3_db_enabled(self) -> bool:
        return bool(
            getattr(self._settings, "sqlserver_enabled", False)
            and self._settings.sqlserver_effective_connection_string
        )

    def _get_v3_sql_client(self) -> SqlServerClient:
        if self._v3_sql_client is not None:
            return self._v3_sql_client
        client = SqlServerClient(self._settings.require_sqlserver_connection_string())
        with client.cursor() as cur:
            cur.execute("SELECT 1")
        self._v3_sql_client = client
        return self._v3_sql_client

    def _build_sql_repository_or_memory(
        self,
        *,
        backend_info_name: str,
        sql_error_subject: str,
        build_sql: Callable[[SqlServerClient], _RepoT],
        build_memory: Callable[[], _RepoT],
    ) -> _RepoT:
        """Shared v3 pattern: SQL when enabled and connectable, else memory (with env-controlled fallback)."""
        if not self._v3_db_enabled():
            return build_memory()
        try:
            client = self._get_v3_sql_client()
            repo = build_sql(client)
            logger.info("v3 %s: using SQL backend", backend_info_name)
            return repo
        except Exception as e:
            if not self._v3_allow_in_memory_fallback():
                logger.error(
                    "v3 SQL %s init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s",
                    sql_error_subject,
                    e,
                )
                raise
            logger.warning(
                "v3 SQL %s init failed, falling back to in-memory: %s",
                sql_error_subject,
                e,
            )
            return build_memory()
```

`MemoryAnalyticsRepository` composes other repositories via `self.get_*` (cross-repo consistency matters if backends differ):

```622:650:backend/src/runtime/app_container.py
    def get_analytics_repo(self) -> AnalyticsRepository:
        if self._analytics_repo is not None:
            return self._analytics_repo

        from src.infrastructure.repositories.memory_analytics_repository import (
            MemoryAnalyticsRepository,
        )
        from src.infrastructure.repositories.sql_analytics_repository import SqlAnalyticsRepository

        def _sql(client: SqlServerClient) -> AnalyticsRepository:
            return SqlAnalyticsRepository(client)

        def _memory() -> AnalyticsRepository:
            return MemoryAnalyticsRepository(
                self.get_inventory_repo(),
                self.get_aisle_repo(),
                self.get_position_repo(),
                self.get_product_record_repo(),
                self.get_review_action_repo(),
                self.get_job_repo(),
            )

        self._analytics_repo = self._build_sql_repository_or_memory(
            backend_info_name="AnalyticsRepository",
            sql_error_subject="analytics repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._analytics_repo
```

Capture session group memory path depends on `get_capture_session_item_repo()`:

```702:725:backend/src/runtime/app_container.py
    def get_capture_session_group_repo(self) -> CaptureSessionGroupRepository:
        if self._capture_session_group_repo is not None:
            return self._capture_session_group_repo

        from src.infrastructure.repositories.memory_capture_session_group_repository import (
            MemoryCaptureSessionGroupRepository,
        )
        from src.infrastructure.repositories.sql_capture_session_group_repository import (
            SqlCaptureSessionGroupRepository,
        )

        def _sql(client: SqlServerClient) -> CaptureSessionGroupRepository:
            return SqlCaptureSessionGroupRepository(client)

        def _memory() -> CaptureSessionGroupRepository:
            return MemoryCaptureSessionGroupRepository(self.get_capture_session_item_repo())

        self._capture_session_group_repo = self._build_sql_repository_or_memory(
            backend_info_name="CaptureSessionGroupRepository",
            sql_error_subject="capture_session_group repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._capture_session_group_repo
```

Use-case getters without return type annotations (typing gap):

```767:824:backend/src/runtime/app_container.py
    def get_list_supplier_prompt_configs_use_case(self):
        from src.application.use_cases.manage_supplier_prompt_configs import (
            ListSupplierPromptConfigsUseCase,
        )

        return ListSupplierPromptConfigsUseCase(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            settings=self._settings,
        )

    def get_create_supplier_prompt_config_version_use_case(self):
        from src.application.use_cases.manage_supplier_prompt_configs import (
            CreateSupplierPromptConfigVersionUseCase,
        )

        return CreateSupplierPromptConfigVersionUseCase(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            clock=self.get_clock(),
            settings=self._settings,
        )

    def get_get_active_supplier_prompt_config_use_case(self):
        from src.application.use_cases.manage_supplier_prompt_configs import (
            GetActiveSupplierPromptConfigUseCase,
        )

        return GetActiveSupplierPromptConfigUseCase(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            settings=self._settings,
        )

    def get_activate_supplier_prompt_config_version_use_case(self):
        from src.application.use_cases.manage_supplier_prompt_configs import (
            ActivateSupplierPromptConfigVersionUseCase,
        )

        return ActivateSupplierPromptConfigVersionUseCase(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
        )

    def get_get_supplier_prompt_config_use_case(self):
        from src.application.use_cases.manage_supplier_prompt_configs import (
            GetSupplierPromptConfigUseCase,
        )

        return GetSupplierPromptConfigUseCase(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
        )
```

`get_clock` returns a new adapter each call (not cached):

```474:477:backend/src/runtime/app_container.py
    def get_clock(self) -> Clock:
        from src.infrastructure.adapters.clock import UtcClock

        return UtcClock()
```

`SqlServerClient.cursor` closes the connection per use (lifecycle context for “no container dispose” today):

```36:60:backend/src/database/sqlserver.py
    @contextmanager
    def cursor(self) -> Generator["pyodbc.Cursor", None, None]:
        """Yield a cursor; connection is closed on exit. Commits on success, rolls back on exception."""
        conn: Optional[pyodbc.Connection] = None
        try:
            conn = pyodbc.connect(self._connection_string)
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:  # nosec B110
                    # Best-effort rollback after primary SQL failure (connection may be invalid).
                    pass
            logger.exception("SQL Server operation failed: %s", e)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:  # nosec B110
                    # Best-effort close so original error still propagates.
                    pass
```

---

## 17. Status

| Item | State |
|------|--------|
| Production code modified | **No** |
| Audit artifact | **`audit/app_container_modularization_audit.md`** (this file) |

**End status:** `APP_CONTAINER_REFACTOR_RECOMMENDED`

---

## Phase C1 implementation note

**Added**

- `backend/src/runtime/container/repository_backend.py`: `RepositoryBackendMode`, `RepositoryBackendResolution`, `resolve_repository_backend_mode` (pure resolver; no repository imports).
- `backend/src/runtime/container/__init__.py`: re-exports resolver symbols.
- `AppContainer`: cached `_repository_backend_resolution`, `_probe_sql_for_repository_backend`, `_get_repository_backend_resolution` with one-shot INFO/WARNING logging (`mode`, `sqlserver_enabled`, `fallback_allowed`, `reason` when set).
- `_build_sql_repository_or_memory` now consults the cached resolution first (`MEMORY_ONLY` / `MEMORY_FALLBACK` → memory without re-probing; `SQL` → existing try/except around `build_sql` preserved for per-repo constructor failures).

**Intentionally unchanged**

- Public `get_app_container`, `reset_app_container_for_tests`, all public `get_*` method names and signatures.
- Default `V3_ALLOW_IN_MEMORY_FALLBACK` behavior.
- API routes, workers, migrations, artifact storage, supplier prompt wiring.
- No new third-party dependencies.

**Tests**

- `backend/tests/runtime/test_repository_backend.py`: resolver cases (memory-only, SQL success, memory fallback, re-raise, fallback callable).
- `backend/tests/runtime/test_app_container.py`: resolution object identity when SQL disabled, `SqlServerClient` not constructed when SQL disabled, single fake SQL client construct across two repos when SQL is enabled.

**Validation (local)**

- `.venv/bin/python -m pytest tests/runtime/test_repository_backend.py tests/runtime/test_app_container.py -q`
- `.venv/bin/ruff check src/runtime/container/ src/runtime/app_container.py tests/runtime/test_repository_backend.py tests/runtime/test_app_container.py`
- `.venv/bin/mypy src/runtime/container/repository_backend.py src/runtime/app_container.py`

**Next step (future phase)**

- Drive all repository construction strictly from the cached `RepositoryBackendMode` (and optionally invalidate or fail-fast on mixed per-repo `build_sql` failures) so mixed SQL/memory backends cannot occur after a successful SQL probe.
