# Dinamic Inventory — Platform and pipeline reference

Summary for the Repo Assistant skill. Product = **operational platform (v3)** + **CV processing subsystem**.

---

## Part 1 — Platform (v3)

### Backend structure (src/)

| Area | Path | Role |
|------|------|------|
| **api** | `api/routes/`, `api/schemas/`, `api/dependencies.py` | HTTP layer: v3 routes (inventories_v3), request/response schemas, dependency injection (repos, use cases, clock, job queue). |
| **application** | `application/use_cases/`, `application/ports/` | Use cases (create/list inventory, create/list aisles, start aisle processing, get aisle status). Ports: repositories (ABCs), services (JobQueue, ArtifactStorage, etc.), contracts (typed payloads). |
| **domain** | `domain/inventory/`, `domain/aisle/`, `domain/jobs/`, etc. | Entities: Inventory, Aisle, Job, SourceAsset, Position, ProductRecord, Evidence, ReviewAction. Status enums and transitions. Framework-agnostic. |
| **infrastructure** | `infrastructure/repositories/`, `infrastructure/queue/` | SQL and in-memory repository implementations; v3 job queue adapter (enqueue job_type + payload → job_id). |
| **database** | `database/schema.sql`, `database/sqlserver.py` | v3 tables: inventories, aisles, inventory_jobs. Legacy jobs table for existing pipeline. |

### v3 API (relevant endpoints)

- `POST/GET /api/v3/inventories` — create, list.
- `GET /api/v3/inventories/{id}` — get inventory.
- `POST/GET /api/v3/inventories/{id}/aisles` — create aisle, list aisles (with optional latest_job).
- `POST /api/v3/inventories/{id}/aisles/{aisle_id}/process` — start aisle processing (202 + job_id).
- `GET /api/v3/inventories/{id}/aisles/{aisle_id}/status` — aisle + latest job status.

Contracts: Pydantic schemas in `api/schemas/`; errors → 404, 409, 422 with detail.

### Frontend (frontend/src/)

- **api:** `client.ts` (getInventories, getAisles, startAisleProcessing, etc.), `types.ts` (Inventory, Aisle, JobSummary, etc.).
- **pages:** InventoriesList, InventoryDetail (with aisles, process action, status, refresh).
- **components:** CreateInventoryDialog, CreateAisleDialog.
- **utils:** formatDate, etc. Align types with backend; handle loading/error/empty states.

---

## Part 2 — CV pipeline (src/)

| Area | Modules | Role |
|------|---------|------|
| **models** | `schemas.py`, contracts | Pydantic schemas, MinifiedTrackResult, PalletObservation, PalletTrack |
| **video** | `ingest.py`, `frames.py` | Video load, frame extraction |
| **detection** | `pallet_detector.py`, clustering | Pallets per frame → List[BBox] |
| **tracking** | `tracker.py`, `track_builder.py` | BBox stream → stable pallet_track_id, List[PalletTrack] |
| **roi** | `cropper.py`, `quality.py` | Crop ROI, blur score |
| **view_selection** | `selector.py`, diversity | 3–5 views per track |
| **llm** | `prompts.py`, `gemini_client.py` | 1 request per track → MinifiedTrackResult |
| **validation** | segregation, determinism, normalizer | One product per pallet, strict counting |
| **reid** | signature, gating, phash, clip_embedder, merge | Track merging |
| **pipeline** | orchestrator, stages / hybrid_inventory_pipeline | run_pipeline(video_path, config) |
| **io** | `outputs.py`, `logging.py` | final_result.json, errors.json, logs |

### Key data contracts (CV)

- **detection:** `detect_pallets_per_frame(frame) -> List[BBox]`
- **tracking:** `update(detections)` → `get_tracks()`; `build_pallet_tracks(...) -> List[PalletTrack]`
- **view_selection:** `select_views_per_track(track, min_views, target_views, max_views) -> List[PalletObservation]`
- **llm:** `analyze_track(track_id, roi_paths, prompt_profile) -> MinifiedTrackResult`
- **validation:** one product per pallet; StrictCountingPolicy; UNKNOWN when evidence insufficient
- **export:** `final_result.json` (OK), `errors.json` (ERROR: MIXED_SKUS, INSUFFICIENT_EVIDENCE)

### Config (src/config.py)

Env-driven: GEMINI_API_KEY, EXTRACT_FPS, MAX_FRAMES_TO_SEND, RESIZE_MAX_SIDE, OUTPUT_DIR, sqlserver_enabled, etc. All thresholds and limits configurable; no literals.
