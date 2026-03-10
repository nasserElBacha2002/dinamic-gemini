# V3.0 Audit — Épica 2 Final Review

## 1. Executive verdict

**READY for next slice**

Épica 2 keeps the intended layering intact: the router stays thin, use cases stay framework-agnostic, and persistence is confined to infrastructure. The SQL repository implements the port correctly with parameterized queries, domain-owned timestamps, observable handling of invalid status, and deterministic ordering. Dependency wiring is centralized and the fallback policy is explicit and configurable. The schema is adequate for this stage and the aisles table is ready for AisleRepository. No critical or high-severity issues were found; the remaining points are minor or deferrable.

---

## 2. What is correct

- **Dependency direction:** The v3 route module imports only `src.api.dependencies`, `src.api.schemas`, and `src.application.use_cases`. It does not import `src.domain` or infrastructure. Use cases import only ports and domain. Ports import domain and contracts. Infrastructure imports application ports and domain. So **api → application/use_cases → ports → infrastructure** and **application → domain** are respected.

- **Thin API:** `inventories_v3.py` only builds a command from the request, calls the use case, and maps the result to `InventoryResponse`. No business rules, no repository access, no domain types in handler signatures.

- **Framework-agnostic use cases:** `CreateInventoryUseCase` and `ListInventoriesUseCase` depend only on `InventoryRepository` and `Clock`. No FastAPI, no request/response, no SQL.

- **Repository port implementation:** `SqlInventoryRepository` implements all three methods of `InventoryRepository` (save, get_by_id, list_all). Queries are parameterized (`?` placeholders). Row-to-domain mapping uses `_ensure_utc()` for datetimes and logs a warning when status is invalid, then falls back to DRAFT.

- **Timestamp policy:** Save uses only entity-owned timestamps (`created_at`, `updated_at`, `completed_at`) for both UPDATE and INSERT. No `now_utc()` in save; the use case sets timestamps via `clock.now()`.

- **Central composition:** `src/api/dependencies.py` is the single place that chooses SQL vs in-memory repo, builds the client, and provides use cases. Route handlers receive use cases via `Depends(...)` and do not reference infrastructure types.

- **Fallback policy:** `V3_ALLOW_IN_MEMORY_FALLBACK` (env) controls whether to fall back to in-memory when SQL is enabled but connection fails. Default is true (dev/test friendly); set to false in production to fail fast. Documented in the module docstring.

- **Request validation:** `CreateInventoryRequest.name` has `min_length=1` and `max_length=255`. API tests assert 422 for empty and over-length name.

- **Schema:** `inventories` and `aisles` match Documento técnico §7.1/§7.2. PKs are string IDs; FK `aisles.inventory_id → inventories(id)`; `UQ_aisles_inventory_code` enforces one code per inventory. DATETIME2 and NVARCHAR sizes are reasonable.

- **Ordering:** Port docstring states that `list_all()` order is implementation-defined and that the SQL implementation uses `created_at DESC`. Implementation matches and is deterministic.

---

## 3. Issues found

### Critical

- **None.**

### High

- **None.**

### Medium

- **SqlInventoryRepository.save() with None timestamps:** If an `Inventory` is constructed with `created_at` or `updated_at` set to `None` (e.g. by mistake or a future loader that doesn’t set them), `_ensure_utc(None)` returns `None` and the INSERT/UPDATE would send NULL into NOT NULL columns and the DB would raise. The use case and current load path always set these, so this is an edge case. **Recommendation:** Either document that callers must set created_at/updated_at, or add a guard at the start of save() that raises a clear error if either is None (deferrable).

### Low

- **MemoryInventoryRepository.list_all() order:** Returns `list(self._store.values())` (insertion order). The port allows implementation-defined order, so this is acceptable. No change required; optionally document in the class docstring for consistency.

- **SQL integration tests leave data:** `test_sql_inventory_repository.py` inserts rows with fixed IDs (`test-epica2-001`, `test-epica2-002`) and does not delete them. Repeated runs keep adding rows if the same DB is used. **Recommendation:** Deferrable: add a teardown or use unique IDs and ignore duplicates; or document that tests assume a dedicated/test DB.

- **Singleton repo lifetime:** `_inventory_repo` is cached for the process. If connection string or `sqlserver_enabled` changes at runtime (e.g. config reload), the process keeps using the first repo until restart. Acceptable for current design; document if config hot-reload is ever required.

---

## 4. Architecture assessment

Layering and dependency direction remain correct after introducing SQL persistence.

- **api:** Depends only on `api.dependencies` and `api.schemas` for v3 inventories; uses application use cases and commands. No domain or infrastructure imports in the route module.
- **application/use_cases:** Depend only on ports (repositories, clock) and domain. No FastAPI, no SQL, no infrastructure.
- **application/ports:** Define abstractions and depend on domain (and contracts). No infrastructure.
- **infrastructure:** Implements ports; depends on application ports and domain. `SqlInventoryRepository` lives in infrastructure and uses `SqlServerClient` from database; the database layer remains a technical detail of the adapter.

Persistence has not leaked into domain or application; the API has not taken on orchestration. The architecture is suitable to add AisleRepository and aisle use cases in the next slice.

---

## 5. Repository and persistence assessment

- **SqlInventoryRepository:** Correctly implements the port. Save uses UPDATE-then-INSERT (rowcount 0) for upsert; all values are parameterized. INSERT and UPDATE both use entity timestamps (after `_ensure_utc()`). Read path maps all columns, normalizes datetimes to UTC-aware, and handles invalid status with a warning and DRAFT fallback. `list_all()` uses `ORDER BY created_at DESC` and documents it. No raw SQL concatenation; no N+1.

- **Schema:** `inventories` has id (PK), name, status, created_at, updated_at, completed_at with appropriate types and nullability. `aisles` has id (PK), inventory_id (FK), code, status, timestamps, error fields, and `UQ_aisles_inventory_code`. Index on `aisles.inventory_id` supports list_by_inventory. Sufficient for this stage and for adding AisleRepository.

- **MemoryInventoryRepository:** Implements the same port; used when DB is disabled or when fallback is allowed and SQL fails. No issues for current scope.

---

## 6. API and dependency wiring assessment

- **Route layer:** Still clean. Two endpoints: POST builds `CreateInventoryCommand`, calls use case, returns `InventoryResponse`; GET calls use case, maps list to `InventoryResponse`. No branching on repo type, no direct repository or DB access.

- **Dependency provisioning:** Centralized in `dependencies.py`. Repo choice is based on `sqlserver_enabled` and non-empty connection string; connectivity is checked with `SELECT 1` before adopting SQL; on failure, behavior depends on `V3_ALLOW_IN_MEMORY_FALLBACK`. Use cases are constructed with `Depends(get_inventory_repo)` and `Depends(get_clock)`. Infrastructure types (SqlServerClient, SqlInventoryRepository, MemoryInventoryRepository, UtcClock) are only referenced inside dependencies, not in route modules. Acceptable for production at this stage; the only caveat is process-scoped repo caching (documented above as low).

---

## 7. Test assessment

- **Use case tests:** `test_create_inventory.py` uses a stub repo and fixed clock, asserts persisted entity and returned entity, and verifies repo state. No framework. Adequate for CreateInventoryUseCase. `test_list_inventories.py` covers list-all and empty list. Adequate.

- **API tests:** `test_inventories_v3_wiring.py` uses TestClient, hits POST and GET, asserts status codes and response shape (id, name, status), and asserts validation (empty name and 256-char name → 422). These validate the vertical slice through the real app and dependency wiring (with in-memory repo when SQL is disabled or unreachable). Adequate for this stage.

- **SQL repository tests:** `test_sql_inventory_repository.py` is gated on DB config (skips when no connection string). It tests save+get_by_id, list_all includes saved, and get_by_id missing returns None. It does not test update path (save existing entity), invalid status read path, or ordering guarantees. For Épica 2, the covered behavior (persist and read back, list) is enough to proceed. Gaps (update, invalid status, ordering) can be covered in the next slice or a follow-up test pass.

Overall, tests are sufficient for this stage: use cases are unit-tested, the API slice is integration-tested, and the SQL repo has conditional integration tests when a DB is available.

---

## 8. Readiness checklist

| Criterion | Yes/No | Justification |
|-----------|--------|----------------|
| Domain remains stable | **Yes** | Inventory entity and InventoryStatus unchanged; no persistence or framework in domain. |
| Use-case boundary remains clean | **Yes** | Use cases depend only on ports and domain; no SQL or API types. |
| API remains thin | **Yes** | Routes only parse, call use case, map response. |
| Repository implementation is acceptable | **Yes** | Sql and memory implementations match the port; SQL uses parameterized queries and documented policies. |
| Dependency wiring is acceptable | **Yes** | Single composition point; configurable fallback; infrastructure hidden from routes. |
| Schema is sufficient for this stage | **Yes** | inventories and aisles match doc; PK/FK and UQ on aisles are correct. |
| Tests are sufficient for this stage | **Yes** | Use case, API, and (when DB present) SQL repo behavior are exercised. |
| No blocking issues remain | **Yes** | No critical or high findings; medium item is a defensive guard and can be deferred. |

---

## 9. Blocking fixes before next slice

**None.** Proceeding to the next slice (e.g. AisleRepository, aisle use cases) is acceptable without further changes.

---

## 10. Deferrable improvements

1. **Guard in SqlInventoryRepository.save():** If `inventory.created_at` or `inventory.updated_at` is None, raise a clear ValueError (or domain-specific error) instead of letting the DB fail. Document that the port expects entities with timestamps set.

2. **SQL integration test cleanup:** Use unique IDs (e.g. UUID) per run or add teardown to delete test rows so repeated runs against the same DB do not accumulate data. Alternatively document that tests require a dedicated/test database.

3. **MemoryInventoryRepository docstring:** State that `list_all()` returns in insertion order (implementation-defined).

4. **Optional: test update path and invalid status:** Add a test that saves an existing entity (update path) and, if feasible, a test that reads a row with an invalid status and asserts the warning and DRAFT fallback (e.g. by inserting raw row and then get_by_id).

---

## 11. Final recommendation

**Proceed to the next slice.** Épica 2 is architecturally sound, persistence is correctly isolated, and the repository and schema are a solid base for adding AisleRepository, aisle use cases, and broader v3 persistence. Apply the deferrable improvements when convenient; they are not blockers for the next stage.
