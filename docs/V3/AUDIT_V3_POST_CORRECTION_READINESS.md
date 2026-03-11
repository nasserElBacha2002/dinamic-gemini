# V3.0 Audit — Post-correction Readiness Review

## 1. Executive verdict

**READY WITH MINOR FIXES**

The dependency direction is correct, use cases are isolated, and the API is thin. The implementation is suitable to start Épica 2. A few non-blocking improvements (composition root, contract strictness, request validation) should be planned so they don’t bite during persistence work.

---

## 2. Strengths

- **Correct dependency direction**  
  - `src/domain` has no imports from `src.application` or `src.api`.  
  - `src/application` (use_cases, ports) imports only domain and contracts; no FastAPI or API types.  
  - `src/api/routes/inventories_v3.py` imports only `src.application` (use_cases, ports for type hints) and `src.api.schemas`; it does **not** import `src.domain`. Routes receive domain entities from `use_case.execute()` and map to Pydantic response models. So **api → application → ports/domain** is respected in code.

- **Use cases are framework-agnostic**  
  - `CreateInventoryUseCase` and `ListInventoriesUseCase` depend only on `InventoryRepository` and `Clock`.  
  - No request/response, no FastAPI. Command in, domain entity (or sequence) out.  
  - Easy to unit-test with stubs and a fixed clock (as in `test_create_inventory.py`, `test_list_inventories.py`).

- **API layer is thin**  
  - `create_inventory`: build `CreateInventoryCommand(name=payload.name)` → `use_case.execute(command)` → `InventoryResponse(id=..., name=..., status=...)`.  
  - `list_inventories`: `use_case.execute()` → list comprehension to `InventoryResponse`.  
  - No business rules, no repository access, no domain logic in the route handlers.

- **In-memory repository matches the port**  
  - `MemoryInventoryRepository` implements all three methods of `InventoryRepository`: `save`, `get_by_id`, `list_all`.  
  - Same contract that a future SQL implementation will implement; no extra or missing methods.

- **Typed contracts exist and are used**  
  - `contracts.py` defines `AnalysisResultPayload`, `MappedPositionPayload`, `InventoryMetricsResult`, `PositionListQuery`, `ProcessAislePayload`.  
  - Service ports reference these types in their method signatures (`analyze_aisle`, `calculate_inventory_metrics`, `map_analysis_to_positions`).  
  - Improves clarity and IDE support at the application boundary.

- **Repository contract clarifications**  
  - `JobRepository.get_latest_by_target(target_type, target_id)` is clearly specified in the docstring.  
  - `PositionListQuery` dataclass gives a single object for filters/pagination instead of many optional parameters.

- **Tests are well-scoped**  
  - Use case tests use `StubInventoryRepo` and `FixedClock`; no HTTP.  
  - Port contract tests assert that stubs satisfy the ABCs.  
  - API wiring test uses `TestClient` and checks status and response shape.

---

## 3. Issues found

### Critical

- **None.**

### High

- **None.**

### Medium

1. **Composition root inside the API route module**  
   - **What:** `_get_inventory_repo()` and `_get_clock()` live in `src/api/routes/inventories_v3.py` and instantiate `MemoryInventoryRepository` and `UtcClock`.  
   - **Why it matters:** When Épica 2 adds a SQL `InventoryRepository`, the choice of implementation (and config such as connection string) will have to be changed in the same file that defines the HTTP routes. That mixes infrastructure wiring with the HTTP layer.  
   - **Recommendation:** Before or during Épica 2, move repo and clock provisioning to a central place (e.g. `src/api/dependencies.py` or `server.py`), and have the route module depend on that. Route module should not import `MemoryInventoryRepository` or `UtcClock` directly.

2. **TypedDict contracts use `total=False` (all keys optional)**  
   - **What:** `AnalysisResultPayload`, `MappedPositionPayload`, `InventoryMetricsResult` are defined with `total=False`, so every key is optional.  
   - **Why it matters:** At type-check time, `{}` is a valid `AnalysisResultPayload`. For Épica 2, when mapping pipeline output to persistence, we need at least `positions` (and likely a defined shape per position). The current types don’t enforce required fields.  
   - **Recommendation:** Either (a) introduce a minimal required-shape TypedDict (e.g. `total=True` with `positions: List[...]`) and use it where the pipeline contract is consumed, or (b) document the required shape in the port docstring and validate at the adapter boundary (e.g. in `ResultMapper` implementation) before persisting.

3. **PositionRepository has two listing methods**  
   - **What:** The port defines both `list_by_aisle(aisle_id, status=..., needs_review=..., ...)` and `list_by_aisle_query(aisle_id, query: Optional[PositionListQuery])`.  
   - **Why it matters:** Any implementation (e.g. SQL in Épica 2) must implement both. That’s redundant and can drift (e.g. one method paginated, the other not).  
   - **Recommendation:** Keep both for now to avoid breaking any future callers. In the SQL implementation, implement `list_by_aisle_query` and have `list_by_aisle` build a `PositionListQuery` from its parameters and call `list_by_aisle_query`. Optionally, in a later refactor, deprecate `list_by_aisle` and migrate callers to `list_by_aisle_query`.

### Low

4. **No validation on `CreateInventoryRequest.name`**  
   - **What:** Pydantic model has `name: str` with no `min_length` or `max_length`.  
   - **Why it matters:** Empty string or very long names are allowed.  
   - **Recommendation:** Add `min_length=1` and a reasonable `max_length` (e.g. 255) on the schema, or validate in the use case and raise a domain-style error. Prefer schema validation for HTTP boundary.

5. **`list_all()` ordering not specified**  
   - **What:** `InventoryRepository.list_all()` returns `Sequence[Inventory]` with no ordering guarantee.  
   - **Why it matters:** `MemoryInventoryRepository` uses `list(self._store.values())` (insertion order). A SQL implementation might order by `created_at DESC` for UX; the contract doesn’t forbid or require it.  
   - **Recommendation:** Document in the port docstring that order is implementation-defined (e.g. “Order not specified; implementations may use created_at or name”). No change required for Épica 2.

---

## 4. API vs application assessment

The relationship between `src/api` and `src/application` is **correct and sustainable**:

- The v3 inventories routes **only**:
  - Parse the request (Pydantic).
  - Build a command (e.g. `CreateInventoryCommand(name=payload.name)`).
  - Call the use case.
  - Map the result to a response DTO (`InventoryResponse`).

- The API module does **not**:
  - Import domain entities or enums (it only uses the object returned by the use case and accesses `.id`, `.name`, `.status.value`).
  - Contain business rules, validation beyond schema, or repository usage.
  - Know about infrastructure beyond what is injected via `Depends` (and the injection is currently in the same module, which is the medium issue above).

So the direction **api → application/use_cases → ports** is real and correctly implemented for the v3 inventories slice. This is a sound base for adding more use cases and persistence in Épica 2.

---

## 5. Contract readiness for Épica 2

- **Repositories**  
  - `InventoryRepository` (save, get_by_id, list_all) is stable and implemented by `MemoryInventoryRepository`. A SQL implementation can be added without changing the port.  
  - `AisleRepository` and others are already defined; no changes required to start implementing SQL for inventories (and later aisles).

- **Typed contracts**  
  - They are good enough to start Épica 2: pipeline output can be typed as `AnalysisResultPayload`, and persistence code can expect `positions` and validate at runtime if needed.  
  - Improving required-field guarantees (see issue 2 above) is recommended but not blocking.

- **Use-case inputs/outputs**  
  - Commands are simple dataclasses; use cases return domain entities.  
  - No framework types in use-case signatures. Stable for adding `CreateAisleUseCase` and similar in Épica 2.

**Conclusion:** Repositories, typed contracts, and use-case boundaries are stable enough to begin SQL persistence and Épica 2.

---

## 6. Épica 2 readiness checklist

| Criterion | Yes/No | Justification |
|-----------|--------|----------------|
| Domain stable enough | **Yes** | Inventory (and existing v3 entities) match Documento técnico §7. No need to change domain for adding SQL persistence. |
| Use-case boundary established | **Yes** | Create/List inventory use cases depend only on ports and domain; no framework or API types. |
| API thin enough | **Yes** | v3 routes only parse → command → execute → map to DTO. No business logic. |
| Repository contracts stable enough | **Yes** | `InventoryRepository` is minimal and clear; in-memory impl matches. SQL can implement same interface. |
| Typed contracts good enough | **Yes** | TypedDicts and PositionListQuery are in place. Optional keys are a documentation/runtime-validation concern, not a blocker. |
| No blocking architectural issues | **Yes** | Dependency direction is correct; no critical or high-severity issues. Medium issues are improvements, not blockers. |

---

## 7. Blocking fixes before Épica 2

**None.** You can start Épica 2 (e.g. SQL `InventoryRepository`, tables, and wiring) with the current code. The medium issues can be addressed in parallel or shortly after.

---

## 8. Deferrable improvements

1. **Move composition root out of the route module**  
   Provide `InventoryRepository` and `Clock` from a central place (e.g. `src/api/dependencies.py` or `server.py`) based on config, and inject them into the v3 routes. The route module should not import `MemoryInventoryRepository` or `UtcClock`.

2. **Tighten TypedDict contracts**  
   Define a minimal required shape (e.g. `positions` required) for the pipeline output consumed by `ResultMapper`, or document and validate at the adapter boundary.

3. **Validate `CreateInventoryRequest.name`**  
   Add Pydantic `min_length=1` and `max_length=255` (or similar) on `CreateInventoryRequest`.

4. **Document `list_all()` ordering**  
   In `InventoryRepository.list_all()` docstring, state that order is implementation-defined.

5. **Implement `list_by_aisle` via `list_by_aisle_query`**  
   In the future SQL `PositionRepository`, implement `list_by_aisle_query` and have `list_by_aisle` build a `PositionListQuery` and delegate. Reduces duplication and keeps behavior consistent.

---

## 9. Final recommendation

- **Proceed to Épica 2.**  
- **Optional before starting:** Move repo and clock provisioning to a central dependencies module so that when you add a SQL `InventoryRepository`, you only change config and the dependency provider, not the route file.  
- **During Épica 2:** Add SQL implementation of `InventoryRepository`, keep the same port, and switch the app to use it via the (current or refactored) composition root. Add validation or stricter types at the pipeline→persistence boundary as you implement the mapper.

The current v3.0 correction pass is technically sound and ready to move into Épica 2, with minor, non-blocking improvements called out for clarity and maintainability.
