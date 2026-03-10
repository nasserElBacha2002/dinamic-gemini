# Épica 6 — Implementation Note: Pipeline Integration and Result Persistence

## 1. Backlog interpretation for Épica 6

- **Épica 6 (Backlog):** "Adaptación del pipeline al dominio" — persist results as Position, ProductRecord, Evidence.
- **HU-6.1:** Transform pipeline output into persisted Position entities (ResultMapper, persist step).
- **HU-6.2:** Each position has evidence; at least one primary.
- **HU-6.3:** ProductRecord per position.
- **Documento técnico §9.4:** Pipeline output contract: positions[] with id, confidence, needs_review, primary_evidence_id, products[] (sku, description, quantity, confidence). §10.5–10.6: pipeline produces positions/products/evidence; result is mapped to domain and persisted.
- **API (§12):** `GET /aisles/{aisleId}/positions` (with pagination/filters §9.7), `GET /positions/{positionId}`.

## 2. Current state summary

- **v3 platform:** Inventories, aisles, v3_jobs, source_assets, upload/list assets, StartAisleProcessingUseCase (enqueues job with payload `{aisle_id}`), GET/POST assets.
- **Pipeline:** HybridInventoryPipeline (InputPreparation → FrameAcquisition → Analysis → EntityResolution → Evidence → Reporting). Input: `JobInput` with either `video_path` (video) or `input_type=photos` + `input_manifest_path` + `photos_dir`. Output: `hybrid_report.json` with `entities[]` (entity_uid, entity_type, pallet_id, internal_code, product_label_quantity, final_quantity, confidence, count_status, evidence_path, etc.).
- **Worker:** Consumes from legacy queue (`dequeue` → job_id). `run_job(base_path, job_id)` loads job via `get_job(base_path, job_id)` (legacy JobRecord from FS/DB). For v3-enqueued job_id (UUID), there is no legacy job → get_job returns None → worker skips. So **v3 process_aisle jobs are never executed**.
- **Domain:** Position, ProductRecord, Evidence entities exist. Repository ports exist (PositionRepository, ProductRecordRepository, EvidenceRepository). No SQL tables or implementations yet for positions/product_records/evidences.

## 3. What is already implemented before Épica 6

- Domain entities: Position, ProductRecord, Evidence (and enums).
- Repository ports: PositionRepository, ProductRecordRepository, EvidenceRepository (contracts only).
- v3 jobs: created and enqueued by StartAisleProcessingUseCase; persisted in v3_jobs; not consumed by worker.
- Source assets: stored under output_dir/v3_uploads/aisles/{aisle_id}/raw/; list_by_aisle available.
- Pipeline: works with video_path or photos (manifest + photos_dir); writes hybrid_report.json and evidence under run_dir.

## 4. What is missing to truly integrate the original pipeline

1. **V3 job consumption:** Worker must recognize v3 job_id, load Job from v3_jobs, execute process_aisle (resolve assets → build pipeline input → run pipeline → map report → persist results → update job and aisle).
2. **Pipeline input from v3 assets:** Given aisle_id, load source assets; if one video → use its full path as video_path; if only photos → copy/link to job_dir/input_photos, write input_manifest.json, use photos_dir + input_manifest_path.
3. **Result mapping:** Map hybrid_report "entities" to v3 Position (one per entity), ProductRecord (one per entity: internal_code, product_label_quantity), Evidence (evidence_path → storage_path, entity_type=position, entity_id=position_id).
4. **Persistence:** SQL (and in-memory) repositories for Position, ProductRecord, Evidence; schema for positions, product_records, evidences.
5. **Job/aisle status:** On pipeline success → persist results, job status RUNNING→SUCCEEDED, aisle PROCESSING→PROCESSED (or in_review). On failure → job FAILED, aisle FAILED with error_message.
6. **API:** GET .../inventories/{inv_id}/aisles/{aisle_id}/positions, GET .../inventories/{inv_id}/aisles/{aisle_id}/positions/{position_id} (or GET .../positions/{position_id} scoped by aisle). Backlog §12 uses GET /aisles/{aisleId}/positions and GET /positions/{positionId}; current API prefix is /api/v3/inventories so we use GET .../aisles/{aisle_id}/positions and GET .../positions/{position_id} under same prefix for consistency.
7. **Frontend:** Show that results exist; link to positions list; minimal positions list and position detail.

## 5. Original pipeline entrypoint(s) and output shape

- **Entrypoint:** `HybridInventoryPipeline.process_video(video_path, mode="hybrid", settings=..., video_id=job_id, output_path=base_path, run_id="run", logger=..., progress_callback=..., job_input=JobInput(...))`. Returns 0 on success, 1 on stage failure.
- **Input:** JobInput: either video_path (str) + input_type="video", or input_type="photos" + input_manifest_path + photos_dir (paths relative to job dir / run dir as per InputPreparationStage).
- **Output:** hybrid_report.json in run_dir with: report_version 2.1, entities[] where each has entity_uid, entity_type, pallet_id, internal_code, product_label_quantity, final_quantity, confidence, count_status, evidence_path (relative to run_dir), evidence_localization, etc. Evidence files written under run_dir/evidence/<slug>/ by EvidenceStage.

## 6. Target v3 result model for this epic

- **Position:** id, aisle_id, status=detected, confidence, needs_review (from count_status or confidence), primary_evidence_id, created_at, updated_at, detected_summary_json (optional), corrected_summary_json (optional). One Position per report entity (pallet/position).
- **ProductRecord:** id, position_id, sku (internal_code or "unknown"), description (optional), detected_quantity (product_label_quantity or final_quantity), confidence, created_at, updated_at, corrected_quantity=None. One ProductRecord per entity (current pipeline has one product per entity).
- **Evidence:** id, entity_type="position", entity_id=position.id, type=position_crop (or from path), storage_path (resolvable path: e.g. relative to output root), source_asset_id (optional; we may not have it from pipeline), is_primary=True for first evidence of position, frame_index/timestamp_ms/bbox_json/quality_score optional. One Evidence per position from evidence_path (run_dir/evidence_path).

## 7. Backend files to create

- `src/database/schema.sql` — add positions, product_records, evidences tables (append).
- `src/infrastructure/repositories/memory_position_repository.py`
- `src/infrastructure/repositories/sql_position_repository.py`
- `src/infrastructure/repositories/memory_product_record_repository.py`
- `src/infrastructure/repositories/sql_product_record_repository.py`
- `src/infrastructure/repositories/memory_evidence_repository.py`
- `src/infrastructure/repositories/sql_evidence_repository.py`
- `src/infrastructure/pipeline/v3_report_mapper.py` — map hybrid_report entities → Position, ProductRecord, Evidence (domain).
- `src/application/use_cases/persist_aisle_result.py` — PersistAisleResultUseCase (mapper + repos + clock).
- `src/application/use_cases/list_aisle_positions.py` — ListAislePositionsUseCase.
- `src/application/use_cases/get_position_detail.py` — GetPositionDetailUseCase.
- `src/infrastructure/pipeline/v3_job_executor.py` — execute v3 process_aisle: load job, assets, prepare input, run pipeline, load report, persist result, update job/aisle.
- `src/api/schemas/position_schemas.py` — PositionResponse, PositionDetailResponse, ProductRecordResponse, EvidenceResponse.
- Tests: `tests/application/use_cases/test_persist_aisle_result.py`, `tests/application/use_cases/test_list_aisle_positions.py`, `tests/infrastructure/pipeline/test_v3_report_mapper.py`, API tests for GET positions and GET position.

## 8. Backend files to modify

- `src/database/schema.sql` — add CREATE TABLE for positions, product_records, evidences.
- `src/api/dependencies.py` — add get_position_repo, get_product_record_repo, get_evidence_repo, get_persist_aisle_result_use_case, get_list_aisle_positions_use_case, get_get_position_detail_use_case; wire v3 job executor (or keep it in worker with direct repo access for simplicity).
- `src/api/routes/inventories_v3.py` — register GET .../aisles/{aisle_id}/positions, GET .../positions/{position_id} (or under inventories context).
- `src/jobs/worker.py` — in run_job, try load v3 job; if process_aisle run v3 executor; else legacy run_job path.
- `src/app.py` or server: no change if worker stays in server background thread.

## 9. Frontend files to create

- (Optional) `frontend/src/pages/AislePositionsPage.tsx` or integrate into InventoryDetail as "View results" link and a simple positions list section.
- `frontend/src/pages/PositionDetailPage.tsx` — minimal: position info, products list, evidence placeholder.

## 10. Frontend files to modify

- `frontend/src/api/types.ts` — PositionSummary, ProductRecordSummary, EvidenceSummary, PositionDetail, list positions response.
- `frontend/src/api/client.ts` — getAislePositions(inventoryId, aisleId), getPositionDetail(inventoryId?, positionId) or getPositionDetail(positionId).
- `frontend/src/pages/InventoryDetail.tsx` — show "Results" / "N positions" when job succeeded; link to positions list or inline expand.
- Router: add route for positions list (e.g. /inventories/:invId/aisles/:aisleId/positions) and position detail (e.g. /positions/:positionId or under inventory).

## 11. Backend design summary

- **V3 job executor:** Standalone function or class in infrastructure: `execute_v3_process_aisle(job_id, base_path, settings, v3_repos, pipeline_factory)`. Loads Job from v3_jobs, gets aisle_id from payload, loads SourceAssets for aisle, builds JobInput (video or photos under base_path/job_id/), runs HybridInventoryPipeline, reads hybrid_report.json, calls ResultMapper (report → domain list), then PersistAisleResultUseCase to save Position/ProductRecord/Evidence, then update Job (SUCCEEDED) and Aisle (PROCESSED). On any failure: Job FAILED, Aisle FAILED with error_message.
- **Result mapper:** Map each report entity to: 1 Position (id=entity_uid or new UUID, aisle_id, confidence, needs_review from count_status, primary_evidence_id from first evidence id we generate), 1 ProductRecord (position_id, sku=internal_code or "unknown", detected_quantity=final_quantity or product_label_quantity), 1 Evidence (entity_type=position, entity_id=position.id, storage_path=run_dir/evidence_path or relative path, is_primary=True). Mapper receives run_dir and report dict; returns lists of Position, ProductRecord, Evidence (with IDs assigned).
- **Repositories:** Standard save/get_by_id/list_by_aisle (Position), list_by_position (ProductRecord, Evidence). SQL tables: positions (id, aisle_id, status, confidence, needs_review, primary_evidence_id, created_at, updated_at, detected_summary_json, corrected_summary_json); product_records (id, position_id, sku, description, detected_quantity, corrected_quantity, confidence, created_at, updated_at); evidences (id, entity_type, entity_id, type, storage_path, source_asset_id, is_primary, frame_index, timestamp_ms, bbox_json, quality_score). FKs: position→aisle, product_record→position, evidence (entity_id references position when entity_type=position).
- **List positions:** ListAislePositionsUseCase: validate aisle exists and belongs to inventory, call position_repo.list_by_aisle(aisle_id, optional query). Return list of Position (or DTOs). Pagination/filters per §9.7 can be minimal in this epic (page, page_size; status, needs_review, min_confidence, sku as optional query params).
- **Get position detail:** GetPositionDetailUseCase: load position by id; validate; load products by position_id, evidences by entity_type+entity_id; return composite DTO.

## 12. Frontend design summary

- **InventoryDetail:** Add column or badge "Results" / "N positions" when aisle.status is processed (or job latest_job status succeeded). Button or link "View results" → navigate to /inventories/:invId/aisles/:aisleId/positions.
- **Positions list page:** Route /inventories/:invId/aisles/:aisleId/positions. Fetch getAislePositions(invId, aisleId). Show table: position id, status, confidence, needs_review, products summary, link to detail. Empty state when no positions. Loading and error states.
- **Position detail page:** Route /positions/:positionId (or /inventories/:invId/aisles/:aisleId/positions/:positionId). Fetch getPositionDetail(positionId). Show position fields, products table, evidence (image if storage_path is usable; else placeholder). Minimal; no review actions in this epic.

## 13. Risks / decisions

- **Worker and v3 repos:** Worker runs in background thread; it cannot use FastAPI Depends. So we need to instantiate v3 repos (and executor) inside the worker when handling v3 jobs. Use the same dependency helpers (get_aisle_repo, etc.) by importing and calling them, or a dedicated `get_v3_repos_for_worker()` that returns (job_repo, aisle_repo, source_asset_repo, position_repo, product_repo, evidence_repo, clock, artifact_storage_base_path). Decision: from worker call into a single `execute_v3_process_aisle(job_id, base_path)` that internally loads settings and repos (via config and optional dependency-style getters that read from module-level or env).
- **Asset paths for pipeline:** Pipeline expects video_path as absolute or relative to cwd; for photos, job_input.photos_dir is relative to run_dir.parent (job dir). So we create base_path/job_id/input_photos and base_path/job_id/input_manifest.json; then JobInput(input_type="photos", input_manifest_path="input_manifest.json", photos_dir="input_photos"). InputPreparationStage resolves to run_dir.parent / "input_manifest.json" = base_path/job_id/input_manifest.json and base_path/job_id/input_photos. So we copy or symlink each photo asset file into base_path/job_id/input_photos with a stored_filename (e.g. photo_0.jpg, photo_1.jpg) and manifest with photos: [{index, stored_filename}].
- **Evidence storage_path:** Pipeline writes to run_dir/evidence/<slug>/; report entity has evidence_path relative to run_dir. We persist Evidence.storage_path as relative to output_dir (e.g. job_id/run/evidence/<slug>) so the backend can serve files later or the frontend can request a URL. For this epic we only need to persist the path; serving evidence images can be a later epic.
- **Primary evidence:** First evidence for each position is_primary=True. Report has one evidence_path per entity; we create one Evidence per position.

Implementing next.
