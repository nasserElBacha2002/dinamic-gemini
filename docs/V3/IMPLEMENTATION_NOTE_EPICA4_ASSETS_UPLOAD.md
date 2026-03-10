# Épica 4 — Implementation Note: Upload and asset management (backlog order)

## 1. Backlog interpretation for Épica 4

**V3.0 Backlog — Épica 4 (Upload de assets y storage):**
- **HU-4.1:** Operator uploads multiple photos to an aisle; endpoint `POST /aisles/{aisleId}/assets`; each file creates a `SourceAsset`; aisle transitions to `assets_uploaded`.
- **HU-4.2:** Endpoint supports video; asset typed as `video`; pipeline can later identify photo vs video.
- **Tasks:** Table `source_assets`, implement `ArtifactStorage`, implement `UploadAisleAssetsUseCase`.
- **SourceAsset (backlog + Documento técnico §7.3):** id, aisle_id, type (photo/video), original_filename, storage_path, mime_type, uploaded_at; optional metadata_json.
- **API style:** Current v3 uses `/api/v3/inventories/{inventory_id}/aisles/...`, so we use `POST/GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` for consistency.
- **Content-type validation:** Backlog suggests `_detect_asset_type(content_type)` — support image/* and video/*; reject unsupported types.

## 2. Current state summary

- **Domain:** `SourceAsset` and `SourceAssetType` exist in `src/domain/assets/entities.py`. `Aisle` has `mark_assets_uploaded(now)`.
- **Ports:** `SourceAssetRepository` (save, get_by_id, list_by_aisle) and `ArtifactStorage` (save_file(path, file_obj, content_type) -> str) exist in application ports.
- **Infrastructure:** No `SourceAssetRepository` implementation. Application `ArtifactStorage` has no v3 adapter (pipeline has a different `ArtifactStorage` Protocol with write_json/write_bytes under `src/storage/`).
- **API:** No asset upload or list endpoints. Inventories and aisles routes are under `inventories_v3`.
- **Config:** `output_dir` exists; we use a subdir for v3 uploads (e.g. `output_dir/v3_uploads` or a dedicated setting).

## 3. What was already advanced out of order

- **Processing/jobs (labelled “Épica 4” in a prior note):** That was **Épica 5** (jobs/orchestration): StartAisleProcessingUseCase, GET status, v3_jobs table, POST process. So the **real Épica 4** (upload + storage + SourceAsset persistence) was never implemented.

## 4. What Épica 4 must still implement to restore backlog order

- Persistence for `SourceAsset`: table `source_assets`, SQL and in-memory `SourceAssetRepository`.
- An adapter implementing application port `ArtifactStorage` (save_file) for v3 uploads, writing under a configurable base path.
- `UploadAisleAssetsUseCase`: validate aisle (and optionally inventory), accept list of files, detect type (photo/video), reject unsupported; for each file: save via ArtifactStorage, create and save SourceAsset; then mark aisle `assets_uploaded` and save aisle; return created assets.
- API: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` (multipart/form-data), `GET .../assets` to list assets for an aisle.
- Application exception for unsupported asset type and clear 404 for aisle not found.
- Frontend: upload control per aisle, success/error feedback, minimal asset count/list.

## 5. Backend files to create

- `src/application/errors.py` — add `UnsupportedAssetTypeError` if not present (or use ValueError and map in route).
- `src/application/use_cases/upload_aisle_assets.py` — UploadAisleAssetsUseCase.
- `src/application/use_cases/list_aisle_assets.py` — ListAisleAssetsUseCase (list by aisle; validate aisle belongs to inventory).
- `src/infrastructure/repositories/memory_source_asset_repository.py` — MemorySourceAssetRepository.
- `src/infrastructure/repositories/sql_source_asset_repository.py` — SqlSourceAssetRepository.
- `src/infrastructure/storage/v3_artifact_storage_adapter.py` — Implements application ArtifactStorage; writes to base path, returns path string.
- `src/api/schemas/asset_schemas.py` — SourceAssetResponse, UploadAisleAssetsResponse.
- Tests: `tests/application/use_cases/test_upload_aisle_assets.py`, `tests/api/test_aisle_assets_v3.py`; extend schema or add migration for `source_assets`.

## 6. Backend files to modify

- `src/database/schema.sql` — Add table `source_assets`.
- `src/application/errors.py` — Add `UnsupportedAssetTypeError`.
- `src/api/dependencies.py` — Register SourceAssetRepository (getter), ArtifactStorage (v3 adapter), upload and list use cases.
- `src/api/routes/inventories_v3.py` — Add POST and GET for `.../aisles/{aisle_id}/assets`.
- `src/application/use_cases/__init__.py` — Export new use cases (if present).

## 7. Frontend files to create

- None mandatory; optional small component for upload button + file input if not inline in InventoryDetail.

## 8. Frontend files to modify

- `frontend/src/api/types.ts` — Add SourceAssetSummary, UploadAisleAssetsResponse.
- `frontend/src/api/client.ts` — Add uploadAisleAssets(inventoryId, aisleId, files), getAisleAssets(inventoryId, aisleId).
- `frontend/src/pages/InventoryDetail.tsx` — Add upload UI per aisle (input multiple files, submit, loading/error/success), show asset count or list after load/refresh.

## 9. Backend design summary

- **source_assets table:** id (PK), aisle_id (FK to aisles), type (VARCHAR photo/video), original_filename, storage_path, mime_type, uploaded_at; optional metadata_json. Index on aisle_id.
- **UploadAisleAssetsUseCase:** Input: aisle_id, inventory_id (for validation), list of (filename, file_obj, content_type). Validate aisle exists and aisle.inventory_id == inventory_id; for each file: detect type (image/* -> PHOTO, video/* -> VIDEO), else raise UnsupportedAssetTypeError; storage_path = f"aisles/{aisle_id}/raw/{asset_id}_{sanitized_filename}"; path_returned = artifact_storage.save_file(storage_path, file_obj, content_type); create SourceAsset(..., storage_path=path_returned); asset_repo.save(asset); then aisle.mark_assets_uploaded(clock.now()); aisle_repo.save(aisle); return list of created assets.
- **ListAisleAssetsUseCase:** Input: inventory_id, aisle_id. Load aisle; if not found or aisle.inventory_id != inventory_id raise AisleNotFoundError; return asset_repo.list_by_aisle(aisle_id).
- **V3 ArtifactStorage adapter:** Implements application port. save_file(path: str, file_obj: BinaryIO, content_type: str) -> str: read file_obj to bytes, write to base_path/path (mkdir parents), return path as string (relative or absolute per contract). Base path from config (e.g. output_dir/v3_uploads).
- **API:** POST .../assets: multipart form "files" (multiple); extract UploadFile list; validate at least one file; call use case with inventory_id, aisle_id, list of (filename, file, content_type); return 201 with list of asset summaries. GET .../assets: call ListAisleAssetsUseCase; return 200 with list. 404 if aisle not found or not in inventory; 400 if unsupported type; 422 if no files.

## 10. Frontend design summary

- **Upload:** Per aisle row or section: "Upload" button; file input (multiple, accept="image/*,video/*"); on change submit FormData with files; loading state; on success show message and refetch aisle assets (or list aisles); on error show getApiErrorMessage.
- **Asset visibility:** After upload or on load, show asset count for each aisle (call GET assets when displaying aisle detail or add a small "N assets" from GET assets). Minimal: show count in table or under aisle; optional list of filenames.

## 11. Risks / decisions

- **Two ArtifactStorage definitions:** Application port (save_file) vs pipeline port (write_json, write_bytes). Use only the application port in use cases; v3 adapter implements it with filesystem under base path. No change to pipeline storage.
- **Base path for v3 uploads:** Use `output_dir` from config and subdir `v3_uploads` so path is `output_dir/v3_uploads/aisles/{aisle_id}/raw/...`. Ensures one place for all v3 uploads; config already has output_dir.
- **Sanitize filename:** Use a safe filename (e.g. asset_id + extension from original or ".bin") to avoid path traversal; store original_filename in DB.
- **Empty upload:** Reject with 422 "At least one file is required".
- **Aisle ownership:** Validate aisle belongs to inventory for both POST and GET assets.
