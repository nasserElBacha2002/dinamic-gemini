# Épica 9 — Métricas básicas (backend)

## Before coding — Implementation note

### 1. Backlog interpretation for Épica 9

Épica 9 adds a **basic metrics backend layer** so the system can compute and expose inventory-level metrics from persisted v3 data. The backlog and Documento técnico §9.6 define canonical metrics: `total_positions`, `total_reviewed_positions`, `auto_accepted_positions`, `corrected_positions`, `deleted_positions`, `success_rate`, and optionally `correction_rate` / `deletion_rate`. Metrics are computed at query time (not stored). The implementation must respect the existing architecture (api → use cases → ports → infrastructure) and not put business logic in routes.

### 2. Current backend state summary

- **Ports:** `MetricsCalculator` (application.ports.services) and `InventoryMetricsResult` (application.ports.contracts) already exist. `PositionRepository.list_by_aisles(aisle_ids)` and `AisleRepository.list_by_inventory(inventory_id)` exist.
- **Domain:** `PositionStatus` enum: DETECTED, REVIEWED, CORRECTED, DELETED. Terminal states for “reviewed” = REVIEWED, CORRECTED, DELETED.
- **No prior metrics implementation:** No existing service implementing `MetricsCalculator`; no use case; no route.

### 3. Files identified as relevant

- `src/application/ports/services.py` — MetricsCalculator (unchanged).
- `src/application/ports/contracts.py` — InventoryMetricsResult (docstring tightened).
- `src/application/ports/repositories.py` — AisleRepository.list_by_inventory, PositionRepository.list_by_aisles.
- `src/domain/positions/entities.py` — PositionStatus.
- `src/api/routes/inventories_v3.py` — Add GET `/{inventory_id}/metrics`.
- `src/api/schemas/inventory_schemas.py` — Add response schema.
- `src/api/dependencies.py` — Wire use case.
- `src/runtime/v3_deps.py` — Wire metrics calculator.

### 4. Metrics semantics implemented

- **total_positions:** Count of all positions in the inventory (all aisles).
- **total_reviewed_positions:** Count of positions with status in (reviewed, corrected, deleted).
- **auto_accepted_positions:** Count with status = reviewed.
- **corrected_positions:** Count with status = corrected.
- **deleted_positions:** Count with status = deleted.
- **success_rate:** `auto_accepted_positions / total_reviewed_positions * 100` if total_reviewed > 0, else 0. Rounded to 2 decimals.
- **correction_rate / deletion_rate:** Same denominator; 0 when total_reviewed = 0. Rounded to 2 decimals.

### 5. Backend files created

- `src/infrastructure/services/__init__.py`
- `src/infrastructure/services/inventory_metrics_service.py`
- `src/application/use_cases/get_inventory_metrics.py`
- `tests/infrastructure/services/__init__.py`
- `tests/infrastructure/services/test_inventory_metrics_service.py`
- `tests/application/use_cases/test_get_inventory_metrics.py`
- `tests/api/test_inventory_metrics_api.py`

### 6. Backend files modified

- `src/application/ports/contracts.py` — Docstring for InventoryMetricsResult.
- `src/api/schemas/inventory_schemas.py` — InventoryMetricsResponse.
- `src/runtime/v3_deps.py` — get_metrics_calculator().
- `src/api/dependencies.py` — get_get_inventory_metrics_use_case().
- `src/api/routes/inventories_v3.py` — GET /{inventory_id}/metrics.

### 7. Main risks / likely review points

- TypedDict total=False allows optional keys; API expects all. Mitigated by docstring and service always returning full dict.
- Rounding: three rates may not sum to 100. Documented in service docstring.
- Service called without use case (e.g. missing inventory) returns zeros; use case enforces 404. Acceptable.

### 8. What to self-audit after implementation

- Import order and naming in new modules.
- Edge cases: no aisles, no positions, all detected.
- Contract vs API schema alignment.
- No logic in route; clear 404 handling.

---

## A. Implementation summary

### 1. What was implemented

- **MetricsCalculator implementation:** `InventoryMetricsService` in infrastructure/services: loads aisles for inventory, loads all positions via `list_by_aisles`, counts by terminal status (reviewed, corrected, deleted), computes rates with zero denominator handled. Returns full `InventoryMetricsResult`.
- **Use case:** `GetInventoryMetricsUseCase`: ensures inventory exists (raises `InventoryNotFoundError` otherwise), delegates to `MetricsCalculator`.
- **API:** `GET /api/v3/inventories/{inventory_id}/metrics` returns `InventoryMetricsResponse` (Pydantic) with all eight fields; 404 when inventory not found.
- **Wiring:** `get_metrics_calculator()` in v3_deps; `get_get_inventory_metrics_use_case` in dependencies; route uses Depends.

### 2. Files created

- `src/infrastructure/services/__init__.py`
- `src/infrastructure/services/inventory_metrics_service.py`
- `src/application/use_cases/get_inventory_metrics.py`
- `tests/infrastructure/services/__init__.py`
- `tests/infrastructure/services/test_inventory_metrics_service.py`
- `tests/application/use_cases/test_get_inventory_metrics.py`
- `tests/api/test_inventory_metrics_api.py`

### 3. Files modified

- `src/application/ports/contracts.py` — Docstring for `InventoryMetricsResult`.
- `src/api/schemas/inventory_schemas.py` — `InventoryMetricsResponse`.
- `src/runtime/v3_deps.py` — `get_metrics_calculator`, `MetricsCalculator` import.
- `src/api/dependencies.py` — `get_get_inventory_metrics_use_case`, `GetInventoryMetricsUseCase`, `MetricsCalculator` import.
- `src/api/routes/inventories_v3.py` — Dependency import, schema import, use case import, `get_inventory_metrics` route.

### 4. API contract added

- **Request:** None (path parameter `inventory_id`).
- **Response:** `InventoryMetricsResponse`: total_positions, total_reviewed_positions, auto_accepted_positions, corrected_positions, deleted_positions, success_rate, correction_rate, deletion_rate (all required).

### 5. Tests added

- **Service (5):** zero positions → zeros; zero reviewed (all detected) → zeros; mixed statuses → correct counts and rates; other inventory’s aisles excluded; inventory with no aisles → zeros.
- **Use case (2):** inventory exists → returns calculator result; inventory missing → raises InventoryNotFoundError.
- **API (2):** 200 with correct JSON body; 404 for missing inventory.

---

## B. Self-review + auto-corrections

### 1. Issues detected in first pass

| # | Issue | Severity |
|---|--------|----------|
| 1 | Import order in `inventory_metrics_service.py`: contracts (return type) should come before repositories/services for readability. | Low |
| 2 | Module docstring did not state that the returned dict must include all keys required by the API / §9.6. | Low |
| 3 | Rounding: success_rate + correction_rate + deletion_rate may not sum to 100; no explicit note. | Low |
| 4 | Contract `InventoryMetricsResult` is TypedDict total=False; implementers could omit keys; API would break. | Low |
| 5 | Missing edge-case test: inventory with zero aisles (list_by_aisles([])) to ensure no reliance on repo behavior with empty list. | Medium |

### 2. Corrections applied automatically

- **Import order** in `inventory_metrics_service.py`: reordered to contracts → repositories → services → domain.
- **Module docstring** in `inventory_metrics_service.py`: added that the returned dict includes all keys required by §9.6 / InventoryMetricsResponse, and that rates are rounded to 2 decimals and may not sum to 100.
- **Contract docstring** in `contracts.py`: added that implementations must return all keys so the API layer can serialize without validation errors.
- **New test** `test_metrics_inventory_with_no_aisles_returns_zeros`: inventory with no aisles → all metrics zero (covers list_by_aisles([])).

### 3. Intentionally deferred

- **TypedDict total=True / required keys:** Changing `InventoryMetricsResult` to total=True would force every constructor to pass all keys; current call sites (service + tests) already provide all. Left as total=False to avoid unnecessary churn; docstring documents the requirement.
- **Explicit validation of empty inventory_id in service:** Use case already enforces inventory existence; service with unknown id yields empty aisles and zeros. No change.
- **Rounding strategy (e.g. make rates sum to 100):** Backlog does not require it; rounding to 2 decimals is sufficient. Documented.
- **SqlPositionRepository.list_by_aisles unit test:** Coverage is via integration/API tests and in-memory service tests; SQL repo is exercised elsewhere. Not added in this epic.

### 4. Final confidence assessment

The backend slice is **coherent, testable, and architecturally correct**:

- Metrics logic lives in infrastructure (service), orchestration in application (use case), route is thin and maps only 404.
- Dependency direction is correct (api → use cases → ports; infrastructure implements ports).
- Semantics match §9.6 and the backlog; zero denominator is handled; edge cases (no aisles, no positions, all detected, other inventory’s aisles) are covered by tests.
- Contract and API schema are aligned and documented; obvious issues from the self-review were fixed.

**Verification:** `pytest tests/infrastructure/services/test_inventory_metrics_service.py tests/application/use_cases/test_get_inventory_metrics.py tests/api/test_inventory_metrics_api.py -v` — **9 passed.**
