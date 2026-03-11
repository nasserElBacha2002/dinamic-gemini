# Implementation note — First slice (v3.0)

## 1. Documents reviewed

- **docs/V3/Documento tecnico - 3.0.md** — §7 (domain entities: Inventory, Aisle, SourceAsset, Position, ProductRecord, Evidence, ReviewAction, Job; fields, status enums, transitions), §8 (layers), §9.1–9.2 (repositories and infrastructure contracts: ArtifactStorage, JobQueue, AnalysisProvider, MetricsCalculator, ResultMapper).
- **docs/V3/V3.0 - Backlog.md** — Épica 1 (HU-1.1 domain entities, HU-1.2 application ports), suggested code for Inventory/Aisle, SourceAsset, Position, ProductRecord, Evidence, ReviewAction, Job, and for repositories + services.
- **docs/V3/PLAN_ALINEACION_DOCUMENTACION_V3.md**, **docs/V3/V3.0_DOCUMENTATION_ALIGNMENT_NOTES.md** — alignment notes and open decisions.

## 2. Current architecture summary

- **Domain:** `src/domain/` contains only `entity.py` (v2.1 `Entity`) and `pallet.py` (v2.0 `Pallet`). Used by pipeline (parsing, decision, evidence, reporting, entity_resolution). No v3.0 domain entities.
- **Application:** No `src/application/` layer.
- **Pipeline:** Under `src/pipeline/` with stages, adapters, and pipeline-level ports (`AnalysisProvider`, etc.). Pipeline uses v2.1 RunContext and Entity/Pallet.
- **Infrastructure:** `src/storage/ports/artifact_storage.py`, `src/jobs/ports/job_queue.py` exist with different contracts (write_json/write_bytes vs save_file; enqueue(job_id) vs enqueue(job_type, payload)).
- **API:** `src/api/` with routes and schemas; no use-case orchestration.

## 3. Target v3.0 architecture summary

- **Domain:** Entities Inventory, Aisle, SourceAsset, Position, ProductRecord, Evidence, ReviewAction, Job with explicit status enums; no framework/ORM dependencies.
- **Application:** Use cases depend on ports (repositories + services). Ports defined under `application/ports/`.
- **Infrastructure:** Repositories (SQL), ArtifactStorage (upload), JobQueue (enqueue by type/payload), AnalysisProvider (aisle-scoped), MetricsCalculator, ResultMapper — behind application ports.
- **Interfaces:** REST API and DTOs; controllers call use cases only.

## 4. Key gaps detected

- No v3.0 domain entities.
- No application layer nor application ports.
- Pipeline/storage/jobs ports are pipeline-scoped; v3.0 needs application-scoped contracts (e.g. ArtifactStorage.save_file for uploads, JobQueue.enqueue(job_type, payload) -> str).
- Existing `Entity` and `Pallet` must remain; v3.0 entities live in new domain subpackages.

## 5. Chosen first slice

**HU-1.1 + HU-1.2:** Add v3.0 domain entities and application ports only.

- **In scope:** All entities from Documento técnico §7 (Inventory, Aisle, SourceAsset, Position, ProductRecord, Evidence, ReviewAction, Job) with enums and fields; all repository and service ports from §9.1–9.2.
- **Out of scope:** Persistence, use cases, API changes, pipeline wiring, frontend.

## 6. Why this slice first

- Matches backlog Sprint 1 order (HU-1.1, HU-1.2).
- Establishes contracts and domain model without touching DB or API.
- Unlocks Épica 2 (persistence) and use-case implementation.
- Low risk: additive only; existing imports of `Entity` and `Pallet` unchanged.

## 7. Files to create / modify

**Create:**

- `src/domain/inventory/__init__.py`, `entities.py`
- `src/domain/aisle/__init__.py`, `entities.py`
- `src/domain/assets/__init__.py`, `entities.py`
- `src/domain/positions/__init__.py`, `entities.py`
- `src/domain/products/__init__.py`, `entities.py`
- `src/domain/evidence/__init__.py`, `entities.py` (v3 entity; distinct from `src/evidence` pack generation)
- `src/domain/reviews/__init__.py`, `entities.py`
- `src/domain/jobs/__init__.py`, `entities.py` (v3 Job entity; distinct from `src/jobs` queue/store)
- `src/application/__init__.py`, `src/application/ports/__init__.py`, `repositories.py`, `services.py`
- `tests/domain/v3/` — unit tests for entities and ports
- `docs/V3/IMPLEMENTATION_NOTE_FIRST_SLICE.md` (this file)

**Modify:**

- `src/domain/__init__.py` — export v3 entities (optional namespace) and keep Entity, Pallet.

## 8. Risks / decisions

- **Naming:** `src/domain/evidence/` and `src/domain/jobs/` coexist with `src/evidence` and `src/jobs`; no import conflict as we use full paths.
- **Aisle error fields:** Documento técnico §9.5 adds error_code, error_message, retryable on Aisle for failed state; included in Aisle entity.
- **Job status:** Backlog uses QUEUED, RUNNING, SUCCEEDED, FAILED; Documento técnico does not enumerate Job status; we follow backlog.
- **Application ArtifactStorage/JobQueue:** Defined with v3.0 contract (save_file; enqueue(job_type, payload) -> str). Existing pipeline/storage ports remain unchanged; adapters can bridge later.

---

## Implementation summary (post-slice)

### What was implemented

- **HU-1.1:** All v3.0 domain entities under `src/domain/` subpackages: Inventory, Aisle, SourceAsset, Position, ProductRecord, Evidence, ReviewAction, Job, with status enums and fields per Documento técnico §7. State transition methods on Inventory and Aisle. Aisle includes error_code, error_message, retryable per §9.5.
- **HU-1.2:** Application ports under `src/application/ports/`: all repository ABCs and service ABCs (ArtifactStorage, JobQueue, AnalysisProvider, MetricsCalculator, ResultMapper). PositionRepository includes list_by_aisle with pagination/filters per §9.7.

### Files created

- Domain: `src/domain/{inventory,aisle,assets,positions,products,evidence,reviews,jobs}/` with `__init__.py` and `entities.py`.
- Application: `src/application/__init__.py`, `src/application/ports/__init__.py`, `repositories.py`, `services.py`.
- Tests: `tests/domain/v3/test_entities.py`, `tests/application/ports/test_ports_contract.py`.

### Files modified

- `src/domain/__init__.py` — exports v3.0 entities alongside Entity and Pallet.

### Design decisions

- v3.0 entities in subpackages; Entity and Pallet unchanged. PositionRepository.list_by_aisle has filters and pagination; list_by_aisles(aisle_ids) for metrics. Application ports use v3.0 contract (save_file; enqueue(job_type, payload) -> str).

### Intentionally deferred

- Persistence, use cases, API routes, pipeline wiring, frontend.

### Recommended next slice

**Épica 2 — HU-2.1 + HU-2.2:** Tables inventories/aisles, SQL implementations of InventoryRepository and AisleRepository, CreateInventoryUseCase and ListInventoriesUseCase, endpoints POST/GET /inventories.

### Verification

- `pytest tests/domain/v3/test_entities.py tests/application/ports/test_ports_contract.py -v` — 13 tests pass.
- `from src.domain import Inventory, Aisle, ...; from src.application.ports import InventoryRepository, ...` — imports succeed.
