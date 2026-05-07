# C2 — Supplier Reference Images API Contract and Validations

## 1. Executive summary

**Status:** READY_WITH_OBSERVATIONS (API contract complete; SQL migration CLI status not validated in this environment due to **HYT00** / connectivity.)

Phase C2 exposes supplier-level reference image management under the existing v3 clients router with scoped ownership validation, structured errors, and file serving aligned with inventory visual references. **PUT replace** for a single image is intentionally deferred (narrow slice; follow-up C2.x/C3.x).

---

## 2. Scope implemented

| Endpoint | Implemented |
|----------|-------------|
| `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | Yes |
| `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | Yes |
| `DELETE /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}` | Yes |
| `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file` | Yes |
| `PUT .../reference-images/{image_id}` | Deferred |

---

## 3. Files changed

| Area | Path | Responsibility |
|------|------|----------------|
| Routes | `backend/src/api/routes/v3/clients.py` | List, upload, delete, file endpoints; multipart → use-case DTOs |
| Schemas | `backend/src/api/schemas/supplier_reference_image_schemas.py` | Response models (no internal storage fields) |
| Dependencies | `backend/src/api/services/v3_stored_artifact_access.py` | `resolve_supplier_reference_image_file_response` → same rules as visual refs |
| Dependencies | `backend/src/api/dependencies.py` | `GetSupplierReferenceImageUseCase` wiring |
| Application | `backend/src/application/use_cases/manage_supplier_reference_images.py` | `GetSupplierReferenceImageUseCase` (scoped read) |
| Errors | `backend/src/api/constants/error_wire.py`, `structured_api_http.py`, `error_mapping.py` | `SUPPLIER_REFERENCE_IMAGE_NOT_FOUND` + HTTP detail |
| Tests | `backend/tests/api/test_supplier_reference_images_api.py` | API coverage + env/dotenv-safe settings refresh |
| Tests | `backend/tests/api/test_inventory_visual_references_api.py` | Legacy local file test: refresh cached settings + reset container (parity / isolation) |
| Audit | `audit/phase-c2-supplier-reference-images-api.md` | This document |

---

## 4. API contract

### List — `GET .../reference-images`

- **Response:** `{ "items": [ SupplierReferenceImageResponse, ... ] }`
- **Ordering:** From repository / use case (`created_at` ascending, tie-break `id` ascending — as implemented in C1 repo).

### Upload — `POST .../reference-images`

- **Content-Type:** `multipart/form-data`
- **Fields:** `files` (one or more parts, same convention as inventory visual references), optional `label`, optional `description`.
- **Batch metadata:** When multiple files are uploaded in one POST, **`label` and `description` are applied to every file in the batch** (the same values are persisted on each created row). A single-file upload uses the same rule: optional metadata applies to that sole row.
- **Response:** `{ "items": [ ... ] }` with HTTP **201**.

### Delete — `DELETE .../reference-images/{image_id}`

- **Response:** `{ "deleted": true, "id": "<image_id>" }`

### File — `GET .../reference-images/{image_id}/file`

- **Behavior:** Same as inventory visual references: S3 → **307** presigned redirect; `storage_provider=local` → `FileResponse`; legacy path-only rows when enabled → file under `{OUTPUT_DIR}/v3_uploads`.

### `SupplierReferenceImageResponse` fields

`id`, `client_supplier_id`, `filename`, `mime_type`, `file_size`, `content_type`, `file_size_bytes`, `label`, `description`, `created_at`, `updated_at`.

Internal storage fields (`storage_path`, `storage_key`, `storage_bucket`, `etag`) are **not** exposed in JSON responses.

---

## 5. Ownership validation

Chain enforced by use cases (and file route after `GetSupplierReferenceImageUseCase`):

1. Client exists (`client_id`).
2. Supplier exists (`supplier_id`).
3. `supplier.client_id == client_id`.
4. For image routes: image exists and `image.client_supplier_id == supplier_id`.

Wrong client for a supplier → `CLIENT_SUPPLIER_CLIENT_MISMATCH` (409). Missing image / wrong supplier scope → `SupplierReferenceImageNotFoundError` → structured **404**.

---

## 6. File serving behavior

`resolve_supplier_reference_image_file_response` delegates to `resolve_visual_reference_file_response` so S3 redirect, local file response, and legacy local read flags behave like inventory visual references without changing that helper’s inventory semantics.

---

## 7. Error mapping

| Condition | Structured code (when applicable) | HTTP |
|-----------|-----------------------------------|------|
| Missing client | `CLIENT_NOT_FOUND` | 404 |
| Missing supplier | `CLIENT_SUPPLIER_NOT_FOUND` | 404 |
| Supplier not under client | `CLIENT_SUPPLIER_CLIENT_MISMATCH` | 409 |
| Missing / wrong-scope image | `SUPPLIER_REFERENCE_IMAGE_NOT_FOUND` | 404 |
| Unsupported MIME / empty upload | Existing Phase B / inventory-style mappings | 400 / 422 |

`StoredArtifactAccessError` from file resolution is mapped like inventory visual-reference file routes.

---

## 8. Tests added

- **`backend/tests/api/test_supplier_reference_images_api.py`:** list (empty and populated), upload (multi-file + metadata), delete, ownership negatives, MIME / zero-byte, file redirect (S3 stub), legacy-style local overwrite under `OUTPUT_DIR`, cross-supplier / cross-client file access.
- **Use-case carryover (C1.1):** List/delete edge coverage already present in `test_upload_supplier_reference_images.py` and `test_manage_supplier_reference_images.py` (missing client/supplier/mismatch, delete `storage_key=None` fallback, failed storage delete after DB delete).

---

## 9. Legacy regression validation

Inventory visual reference API and use-case tests are included in the recommended pytest commands below; intended outcome: unchanged behavior, with improved isolation for the legacy local file test (`cached settings` + `reset_app_container_for_tests`).

---

## 10. Validation commands

Executed during C2 completion (from `backend/`):

- `python -m pytest tests/api/test_supplier_reference_images_api.py`
- `python -m pytest tests/application/use_cases/test_upload_supplier_reference_images.py`
- `python -m pytest tests/application/use_cases/test_manage_supplier_reference_images.py`
- `python -m pytest tests/infrastructure/repositories/test_memory_supplier_reference_image_repository.py`
- `python -m pytest tests/infrastructure/repositories/test_sql_supplier_reference_image_repository_unit.py`
- `python -m pytest tests/database/test_migration_0028_supplier_reference_images.py`
- `python -m pytest tests/api/test_inventory_visual_references_api.py`
- `python -m pytest tests/application/use_cases/test_upload_inventory_visual_references.py`
- `python -m pytest tests/application/use_cases/test_manage_inventory_visual_references.py`
- `python -m pytest --collect-only`
- `python -m ruff check src tests`
- `python -m mypy .` — repository-wide run currently reports many **pre-existing** issues across unrelated modules; `python -m mypy tests/api/test_supplier_reference_images_api.py` passes clean for the new API suite file.

Database migration `scripts/db_migrate.py status` / `validate`: **not validated here** — connection failed with **HYT00** login timeout (SQL Server unreachable from this environment / sandbox). Re-run when DB connectivity is available.

---

## 11. Boundaries preserved

- Frontend: **unchanged**
- Pipeline / prompts / `InventoryVisualReferenceResolver` / `AnalysisContext.visual_references`: **unchanged**
- Inventory visual references behavior: **unchanged** (supplier file helper delegates without altering inventory paths)
- No legacy reference migration/copy into supplier rows

---

## 12. Observations / blockers

- **Test isolation:** Calling `reload_settings()` after monkeypatching `OUTPUT_DIR` / `ARTIFACT_*` can restore values from `.env` (`_load_dotenv_files(for_reload=True)`). Tests that need tmp paths now refresh `src.config._settings` via `AppSettings()` from current `os.environ` and reset the app container where needed.
- **SQL Server / ODBC:** Local pytest logs may show fallback to in-memory v3 repos when the ODBC driver is missing; does not block API contract tests.

---

## 13. Recommended next phase

**C3 — Frontend supplier reference images:** API client, hooks, and UI against these endpoints (no pipeline activation).

---

## C2.1 Review fixes

### Tests added

- **`test_upload_supplier_reference_images_without_files_field_returns_422`** — POST with form fields only (no `files` parts): **422** (FastAPI / validation layer).
- **`test_upload_supplier_reference_images_invalid_multipart_part_returns_422`** — multipart part encoded as a file with whitespace-only filename and content type so the route’s `_to_uploaded_supplier_reference_image_files` guard runs; **422** with detail referencing missing filename/content type.  
  *(Truly empty filename/type tuples are not reliably represented as upload parts by `TestClient`; whitespace-only is used as the stable edge case.)*

### Metadata semantics documented

- **`audit/phase-c2-supplier-reference-images-api.md`** — explicit batch metadata bullet under §4 Upload.
- **`backend/src/api/routes/v3/clients.py`** — OpenAPI descriptions on `File` / `Form` parameters for `upload_supplier_reference_images`.
- **`backend/src/api/schemas/supplier_reference_image_schemas.py`** — `UploadSupplierReferenceImagesResponse` docstring.

### Validation results (C2.1)

From `backend/`:

- `python -m pytest tests/api/test_supplier_reference_images_api.py` — pass (**21** tests collected).
- `python -m pytest tests/api/test_inventory_visual_references_api.py` — pass.
- `python -m pytest tests/application/use_cases/test_upload_supplier_reference_images.py` — pass.
- `python -m pytest tests/application/use_cases/test_manage_supplier_reference_images.py` — pass.
- `python -m pytest --collect-only` — pass (**2003** tests collected in this environment).
- `python -m ruff check src tests` — pass.

`scripts/db_migrate.py status` / `validate`: **not run successfully here** — SQL Server connection failed with **HYT00** login timeout (environment / connectivity). Re-run when the database is reachable.

### Unchanged boundaries

- Frontend: **unchanged**
- Pipeline: **unchanged**
- `inventory_visual_references` behavior: **unchanged**
- No legacy reference migration/copy
