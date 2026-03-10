# Implementation note — Architectural correction pass (v3.0)

## 1. Current risk summary

- **API orchestration:** `src/api/routes/jobs.py` performs orchestration directly (create job, persist uploads, enqueue). There is no application use-case layer; the API is the only entrypoint for job creation.
- **No v3 inventories API:** Current API is job-centric (`/api/v1/inventory/jobs`). No endpoints for v3.0 resources (create/list inventories). Application layer exists only as ports; no use cases are invoked.
- **Weak port contracts:** `AnalysisProvider`, `MetricsCalculator`, `ResultMapper`, `JobQueue` use `Dict[str, Any]` and `List[Dict[str, Any]]`, reducing type safety and clarity.
- **Repository ambiguity:** `JobRepository.get_by_target(target_type, target_id)` does not specify whether it returns the active job, the latest job, or any job. Implementations may diverge.
- **Domain vs legacy confusion:** `src/domain/jobs` (v3 Job entity) and `src/jobs` (queue/worker implementation), and `src/domain/evidence` (v3 Evidence entity) vs `src/evidence` (evidence pack generation) can be confused without clear module-level documentation.

## 2. Proposed corrections

1. **Introduce use cases** — Add `src/application/use_cases/` with `CreateInventoryUseCase` and `ListInventoriesUseCase` depending only on `InventoryRepository` and a `Clock` port. No orchestration in API for v3 inventories.
2. **Typed contracts** — Add `src/application/ports/contracts.py` with:
   - `AnalysisResultPayload` (TypedDict): positions, optional aisle_id
   - `MappedPositionPayload` (TypedDict): id, confidence, needs_review, primary_evidence_id, products
   - `InventoryMetricsResult` (TypedDict): total_reviewed_positions, auto_accepted_positions, corrected_positions, deleted_positions, success_rate, etc.
   - `ProcessAislePayload` (TypedDict): aisle_id for queue payload
   - `PositionListQuery` (dataclass): optional filters and pagination for PositionRepository
3. **Clock port** — Add `Clock` protocol with `now() -> datetime` so use cases stay testable and time-aware.
4. **JobRepository** — Replace `get_by_target` with `get_latest_by_target(target_type: str, target_id: str) -> Optional[Job]` and document: "Returns the most recently updated (or created) job for the target, or None."
5. **PositionRepository** — Add `PositionListQuery` dataclass and a new method `list_by_aisle_query(aisle_id: str, query: Optional[PositionListQuery] = None) -> Sequence[Position]`; keep existing `list_by_aisle(...)` for backward compatibility (callers can pass explicit params). Implementations may implement `list_by_aisle` by delegating to `list_by_aisle_query` with a query built from params.
6. **Domain/legacy docstrings** — Add module-level docstrings to `src/domain/jobs`, `src/domain/evidence`, `src/jobs`, `src/evidence` clarifying domain model vs operational/infrastructure.
7. **API integration** — Add new router `src/api/routes/inventories_v3.py` with `POST /api/v3/inventories` and `GET /api/v3/inventories`. Use FastAPI `Depends` to inject use cases; use an in-memory `InventoryRepository` so the API works without DB. Do not change existing job routes.
8. **Tests** — Use case unit tests; port contract tests for new/updated types; lightweight API test that POST/GET inventories returns 200 and uses use case.

## 3. Files to create

- `src/application/ports/contracts.py` — TypedDict/dataclass contracts
- `src/application/ports/clock.py` — Clock protocol
- `src/application/use_cases/__init__.py`
- `src/application/use_cases/create_inventory.py`
- `src/application/use_cases/list_inventories.py`
- `src/infrastructure/__init__.py`
- `src/infrastructure/repositories/__init__.py`
- `src/infrastructure/repositories/memory_inventory_repository.py`
- `src/api/routes/inventories_v3.py`
- `src/api/schemas/inventory_schemas.py` (v3 request/response)
- `tests/application/use_cases/test_create_inventory.py`
- `tests/application/use_cases/test_list_inventories.py`
- `tests/api/test_inventories_v3_wiring.py` (optional lightweight integration)

## 4. Files to modify

- `src/application/ports/repositories.py` — JobRepository: add `get_latest_by_target`, deprecate/remove `get_by_target`; PositionRepository: add `PositionListQuery` and `list_by_aisle_query`
- `src/application/ports/services.py` — Use typed contracts where applicable (AnalysisProvider return type, etc.)
- `src/application/ports/__init__.py` — Export contracts and Clock
- `src/api/server.py` — Include inventories_v3 router; add dependency providers for use cases
- `src/domain/jobs/__init__.py` — Docstring clarifying domain vs src.jobs
- `src/domain/evidence/__init__.py` — Docstring clarifying domain vs src.evidence
- `src/jobs/__init__.py` — Docstring clarifying operational layer
- `src/evidence/__init__.py` — Docstring clarifying pipeline evidence pack (already has some)

## 5. Decisions about API/application interaction

- **v3 under /api/v3/** — New inventories endpoints live under `/api/v3/inventories` so v1 job API remains unchanged. No breaking changes.
- **Dependency injection** — Use FastAPI `Depends()` to provide `CreateInventoryUseCase` and `ListInventoriesUseCase`. Provider builds use case with in-memory `InventoryRepository` and a real-time `Clock` (datetime.utcnow or timezone-aware now). No global state for repo; single instance per app lifecycle for in-memory store.
- **Legacy jobs API** — Do not refactor `create_inventory_job` or other job routes to use use cases in this pass. They remain the existing pipeline entrypoint. Only the new v3 inventories endpoints call use cases.
- **Repository implementations** — In-memory repository is sufficient for this slice so that GET/POST inventories work without a database. SQL implementations remain a later slice.

---

## Final summary (post-implementation)

**What was corrected:** Application use cases (`CreateInventoryUseCase`, `ListInventoriesUseCase`); API v3 only parses, calls use case, serializes. Typed contracts in `contracts.py`; Clock port and UtcClock. JobRepository: `get_latest_by_target`; PositionRepository: `PositionListQuery` and `list_by_aisle_query`. Docstrings on domain/jobs, domain/evidence, src/jobs, src/evidence. New router POST/GET `/api/v3/inventories` with Depends and in-memory repo.

**Files created:** `contracts.py`, `clock.py`; use_cases (create_inventory, list_inventories); infrastructure (adapters/clock, repositories/memory_inventory_repository); api (inventory_schemas, inventories_v3); tests (use_cases, api/test_inventories_v3_wiring).

**Files modified:** application/ports (repositories, services, __init__); api/server; domain/jobs, domain/evidence, jobs, evidence __init__.

**Decisions:** v3 under `/api/v3/inventories`; single in-memory repo per process; legacy job API unchanged. TypedDict for load-bearing contracts only.

**Deferred:** SQL repositories; refactoring legacy job API; lifespan-based DI.

**Next slice:** SQL InventoryRepository and/or CreateAisleUseCase + aisles endpoints; or ProcessAisleUseCase wired to pipeline.
