# Implementation note — Épica 2 persistence (v3.0)

## 1. Files to create

- `src/infrastructure/repositories/sql_inventory_repository.py` — SQL-backed implementation of `InventoryRepository` using `SqlServerClient`.
- `src/api/dependencies.py` — Central composition: `get_inventory_repo()`, `get_clock()`, `get_create_inventory_use_case()`, `get_list_inventories_use_case()`. Chooses SQL repo when `sqlserver_enabled` and connection string set (with connectivity check), else in-memory.
- `tests/infrastructure/repositories/test_sql_inventory_repository.py` — Integration tests for SQL repository (skip when no DB).
- `docs/V3/IMPLEMENTATION_NOTE_EPICA2_PERSISTENCE.md` — This document.

## 2. Files to modify

- `src/database/schema.sql` — Append v3 tables (inventories, aisles).
- `src/api/routes/inventories_v3.py` — Remove local `_get_inventory_repo`, `_get_clock`, and use `Depends(get_inventory_repo)` etc. from `src.api.dependencies`.
- `src/api/schemas/inventory_schemas.py` — Add `min_length=1`, `max_length=255` to `CreateInventoryRequest.name`.
- `src/infrastructure/repositories/__init__.py` — Export `SqlInventoryRepository`.

## 3. Table design summary

**inventories** (Documento técnico §7.1):

| Column       | Type         | Nullable | Notes                    |
|-------------|--------------|----------|--------------------------|
| id          | VARCHAR(36)  | NOT NULL | PK, UUID string          |
| name        | NVARCHAR(255)| NOT NULL |                          |
| status      | VARCHAR(32)  | NOT NULL | draft, processing, ...   |
| created_at  | DATETIME2    | NOT NULL | UTC                      |
| updated_at  | DATETIME2    | NOT NULL | UTC                      |
| completed_at| DATETIME2    | NULL     | UTC                      |

**aisles** (Documento técnico §7.2):

| Column        | Type         | Nullable | Notes                  |
|---------------|--------------|----------|------------------------|
| id            | VARCHAR(36)  | NOT NULL | PK                     |
| inventory_id  | VARCHAR(36)  | NOT NULL | FK → inventories(id)   |
| code          | VARCHAR(64)  | NOT NULL |                        |
| status        | VARCHAR(32)  | NOT NULL | created, queued, ...   |
| created_at    | DATETIME2    | NOT NULL | UTC                    |
| updated_at    | DATETIME2    | NOT NULL | UTC                    |
| error_code    | VARCHAR(64)  | NULL     |                        |
| error_message | NVARCHAR(512)| NULL     |                        |
| retryable     | BIT          | NULL     |                        |

## 4. Repository design summary

- **SqlInventoryRepository** implements `InventoryRepository`. Constructor accepts `SqlServerClient` (or connection string and creates client internally). Uses parameterized queries; `now_utc()` from `src.database.sqlserver` for timestamps. On read, map rows to domain `Inventory` with `InventoryStatus(status_str)` and timezone-aware datetimes (attach UTC if naive).
- **Single place for repo choice:** `dependencies.get_inventory_repo()` calls `load_settings()`; if `sqlserver_enabled` and non-empty `sqlserver_connection_string`, build `SqlServerClient` and `SqlInventoryRepository(client)`; else return `MemoryInventoryRepository()`. Cache the repo instance per process (lazy singleton) so all requests share the same repo.

## 5. Wiring changes

- **dependencies.py:** New module. Functions: `get_inventory_repo() -> InventoryRepository`, `get_clock() -> Clock`, `get_create_inventory_use_case(...) -> CreateInventoryUseCase`, `get_list_inventories_use_case(...) -> ListInventoriesUseCase`. Use FastAPI `Depends` in route handlers by importing these from `src.api.dependencies`.
- **inventories_v3.py:** Remove `_inventory_repo` global and local `_get_inventory_repo`, `_get_clock`. Import `get_inventory_repo`, `get_clock`, `get_create_inventory_use_case`, `get_list_inventories_use_case` from `src.api.dependencies` and use them in `Depends(...)`.

## 6. Risks and decisions

- **Risk:** SQL Server may return naive datetimes. **Decision:** When reading, if `row.created_at.tzinfo is None`, use `datetime.replace(tzinfo=timezone.utc)` so domain entities get timezone-aware datetimes.
- **Risk:** First request may be slower if DB is chosen and connection is cold. **Decision:** Lazy init in `get_inventory_repo()` is acceptable; same pattern as jobs API.
- **Decision:** Do not create AisleRepository in this slice; only inventories table and InventoryRepository are implemented. Aisles table is created for schema completeness so Épica 3 can add AisleRepository without a migration.
- **Decision:** Keep existing use cases unchanged; they already depend only on `InventoryRepository` and `Clock`.
- **Decision:** Connectivity check when building SQL repo so that if DB is unreachable (e.g. timeout), we fall back to in-memory and tests pass without a running DB.

## 7. Corrections (post-review)

- **Timestamp policy:** Domain owns timestamps; repository persists values it receives. `SqlInventoryRepository.save()` uses entity `created_at`/`updated_at` for INSERT and UPDATE (no now_utc() in save).
- **Fallback:** Env `V3_ALLOW_IN_MEMORY_FALLBACK` (default true). When false, SQL enabled but connection fails → fail fast. Set to false in production.
- **Invalid status:** Log warning with value and inventory_id when invalid status from DB; fallback to DRAFT.
- **Ordering:** Port doc: list_all order implementation-defined; SQL uses ORDER BY created_at DESC.
- **Aisles:** UNIQUE(inventory_id, code) in schema. Existing DBs need separate migration to add constraint if desired.
