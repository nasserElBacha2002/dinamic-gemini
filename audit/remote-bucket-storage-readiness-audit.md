# Remote bucket storage readiness audit

**Repository:** Dinamic Inventory v3.0  
**Audit type:** Read-only — local `output` / filesystem → remote bucket (Google Cloud Storage target)  
**Date:** 2026-05-26  
**Scope:** Backend uploads, pipeline artifacts, API serving, frontend display, worker consumption, DB metadata, tests

---

## 1. Executive summary

### Current storage status

The codebase **already implements a provider-aware artifact storage layer**. Production-oriented remote storage exists today as **Amazon S3** (`S3ArtifactStorageAdapter`), not GCS. Local mode stores durable v3 uploads under **`{OUTPUT_DIR}/v3_uploads`** (default `output/v3_uploads`). A **second, parallel use** of `OUTPUT_DIR` holds **ephemeral pipeline/worker run directories** at `{output_dir}/{job_id}/run/...` (frames, hybrid reports, execution logs) before durable copies are published via `worker_durable_artifact_publisher.py`.

Database schema **already includes** `storage_provider`, `storage_bucket`, `storage_key`, `content_type`, `file_size_bytes`, and `etag` on `source_assets`, `evidences`, `supplier_reference_images`, and job report/log columns (migration `0005_add_storage_provider_metadata.sql`). API serving for operator-facing files uses **`v3_stored_artifact_access.py`**: S3 → **307 redirect to presigned URL**; local → **FileResponse** from `v3_uploads`; legacy rows → `storage_path` when `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true`.

The frontend **does not receive raw filesystem paths** for aisle assets in the common path: it calls **`GET .../image-display-url`** and either uses a **presigned HTTPS URL** or **authenticated `GET .../file`** (blob). This aligns with a private GCS bucket + signed URLs.

### Readiness for GCS migration

| Question | Answer |
|----------|--------|
| Is there a storage abstraction? | **Yes** — `ArtifactStore` / `ArtifactStorage`, wired via `AppContainer.get_artifact_storage()` |
| Is GCS implemented? | **No** — only `local` and `s3` in `ArtifactStorageSettings.validate_artifact_storage_provider` |
| Is schema ready? | **Mostly yes** — provider metadata columns exist; `storage_path` retained for legacy |
| Biggest blockers? | (1) Add **GCS adapter** + env config; (2) Eliminate **remaining direct `output_dir` reads** for durable data; (3) **Backfill** legacy rows; (4) Pipeline **temp workspace** policy for prod |
| Main risks? | Dual-path confusion (`v3_uploads` vs job run dirs); legacy `storage_path` rows; HEIC sidecar files on local disk; tests assuming `tmp_path` layout |

### Recommended migration strategy

**Extend the existing `ArtifactStore` pattern** with a `GcsArtifactStorageAdapter` (mirror `S3ArtifactStorageAdapter`: `put_object`, `get_object`, `download_to_path`, `generate_signed_url`). Do **not** introduce a parallel ad-hoc GCS layer. Keep **`ARTIFACT_STORAGE_PROVIDER=local`** for dev/CI; use **`gcs`** in production. Reuse **`image-display-url`** and `resolve_*_file_response` — only the adapter and redirect URL generation change.

Set credentials via **`GOOGLE_APPLICATION_CREDENTIALS`** (file mount in Docker/OpenCloud) rather than embedding JSON in env vars — matches current deployment style (`docker-compose` + `.env`).

### Final status

**`READY_FOR_IMPLEMENTATION_WITH_RISKS`**

Not `BLOCKED_BY_UNKNOWN_STORAGE_FLOW` — flows are traceable. Not pure `NEEDS_REFACTOR_BEFORE_IMPLEMENTATION` — core abstraction exists; work is adapter + boundary hardening + backfill.

---

## 2. Current photo/file storage flow

### 2.1 Aisle source assets (primary inventory photos/videos)

| Step | Component | Detail |
|------|-----------|--------|
| 1. Upload entry | FE `uploadAisleAssets` → `POST /api/v3/inventories/{inv}/aisles/{aisle}/assets` | `FormData` multipart |
| 2. Route | `api/routes/v3/assets.py` | Delegates to upload use case / multipart helper |
| 3. Validation | `AisleSourceAssetMaterializer` | Content-type + extension rules (`_detect_asset_type`) |
| 4. Key layout | `aisle_source_asset_materializer.py` | `uploads/aisles/{aisle_id}/raw/{asset_id}_{safe_filename}` |
| 5. Write | `ArtifactStorage.put_object` (preferred) or `save_file` | Returns `StoredArtifact` with provider metadata |
| 6. Local path | `V3ArtifactStorageAdapter` | File at `{output_dir}/v3_uploads/{key}` |
| 7. S3 path | `S3ArtifactStorageAdapter` | Object in bucket with optional prefix `v3/` |
| 8. DB | `source_assets` | `storage_path` (relative), `storage_provider`, `storage_bucket`, `storage_key`, `content_type`, `file_size_bytes`, `etag` |
| 9. API list | `SourceAssetSummary` schema | Includes `storage_path`; display via separate endpoints |
| 10. FE display | `fetchEvidenceImageDisplay` | `image-display-url` → presigned URL or `/file` |
| 11. Worker | `WorkerInputArtifactResolver.resolve_source_asset` | `download_to_path` to temp under job run dir |
| 12. Cleanup on failure | `delete_file` / `delete_object` on rollback key | Best-effort |

### 2.2 Supplier reference images

| Step | Component | Detail |
|------|-----------|--------|
| Upload | `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | `clients.py` |
| UC | `upload_supplier_reference_images.py` | Path via `supplier_reference_image_storage_path()` → `client_suppliers/{id}/reference_images/{id}.{ext}` |
| DB | `supplier_reference_images` | Same provider metadata pattern as `source_assets` |
| Serve | `GET .../reference-images/{image_id}/file` | `resolve_supplier_reference_image_file_response` |

### 2.3 Capture session staging uploads

| Step | Component | Detail |
|------|-----------|--------|
| Upload | `capture_sessions.py` + `upload_capture_session_staging_items.py` | Multipart to staging |
| Storage | `artifact_storage.save_file(rel_key, ...)` | **Note:** staging path uses `save_file`; when store supports `put_object`, capture flow should align with materializer (heuristic gap) |
| DB | `capture_session_items.staging_storage_key` | Key string, not full provider row on item (materialize copies into `source_assets`) |
| Materialize | Capture materialize UCs | Promote staging → `AisleSourceAssetMaterializer.persist_uploaded_file_as_source_asset` |

### 2.4 Worker pipeline workspace (non-durable until publish)

| Step | Component | Detail |
|------|-----------|--------|
| Workspace | `v3_job_executor.py` | `output_dir / job_id / run` (segment name `run`) |
| Pipeline | `HybridInventoryPipeline` | Writes frames, crops, reports under `output_path` |
| Publish | `worker_durable_artifact_publisher.py` | Copies log/report JSON/CSV to `jobs/{job_id}/run/{filename}` via `ArtifactStore.put_object` |
| DB job row | `inventory_jobs` | `execution_log_storage_key`, `report_*_storage_key`, providers |

### 2.5 Evidence images (pipeline output)

| Step | Component | Detail |
|------|-----------|--------|
| Create | Evidence stage / persist use case | `evidences` table: `storage_path` + provider fields |
| Serve | Position/evidence API routes | Via stored artifact access / file endpoints |

### 2.6 Exports (CSV/ZIP)

| Step | Component | Detail |
|------|-----------|--------|
| Generation | Export use cases | **In-memory / streaming HTTP response** — not persisted to `output/` for v3 inventory exports (verify per endpoint; package export may buffer) |
| Risk | Large package zip | May use temp files — requires manual validation per `export_inventory_package` implementation |

### 2.7 Legacy / parallel paths (out of v3 ArtifactStore)

| Path | Usage |
|------|--------|
| `src/jobs/*` + `output_dir/{job_id}/` | Legacy job.json layout; dev reset scripts |
| `src/storage/adapters/filesystem_artifact_storage.py` | **Unused** by main pipeline (comment: tests/future) |
| `stored_artifact_reader.py` | Fallback read `output_dir/job_id/run/hybrid_report.json` for local-only scenarios |
| `src/roi/cropper.py` | Optional `output_path` for CV debug writes |
| `src/api/photos_handler.py` | Legacy photo handler (Stage 2.2.A) — confirm not mounted |

---

## 3. Inventory of local filesystem dependencies

| Area | File/module | Local path assumption | Operation | Risk if remote-only |
|------|-------------|----------------------|-----------|---------------------|
| Durable uploads | `v3_artifact_storage_adapter.py` | `{output_dir}/v3_uploads/{key}` | write/read/delete | None in local dev; prod uses GCS |
| Storage builder | `storage_builders.py` | `Path(output_dir)/v3_uploads` | configure base | Correct for local mode |
| API serve local | `v3_stored_artifact_access.py` | `output_dir/v3_uploads` | FileResponse | OK for local mode |
| Legacy read | `v3_stored_artifact_access.py` | `storage_path` under v3_uploads | read | Needs legacy flag or backfill |
| Worker resolve | `input_artifact_resolver.py` | legacy_base = v3_uploads | download_to_path → temp | OK if adapter implements download |
| Pipeline workspace | `v3_job_executor.py` | `{output_dir}/{job_id}/run` | write temp | **Still needs local ephemeral disk** in prod |
| Pipeline CV | `hybrid_inventory_pipeline.py`, `roi/cropper.py` | run_dir paths | read/write frames | Temp dir required (OpenCV) |
| HEIC manifest | `api/routes/v3/shared.py`, `assets.py` | manifest JSON beside asset in v3_uploads | read/write | **Sidecar files** must move to object metadata or GCS prefixes |
| Job log bootstrap | `jobs/worker_bootstrap.py` | `output_dir/job_id/worker_launch.log` | write | Dev/diagnostic only |
| Dev reset | `jobs/dev_reset_local_jobs.py` | `output_dir/*` | delete/list | Dev-only |
| Hybrid report fallback | `stored_artifact_reader.py` | `output_dir/job_id/run/hybrid_report.json` | read | Breaks if only in GCS without metadata |
| Docker | `docker-compose.yml` | volume `../data/output:/app/output` | persist | Prod should not rely on container disk for durable data |
| Config | `config.ensure_output_dir` | creates `output_dir` | mkdir | Still needed for pipeline temp |
| Tests | Many under `backend/tests/` | `tmp_path`, `v3_uploads` | fixtures | Must keep local provider in CI |

---

## 4. Database impact

### Tables and columns (file-related)

| Table | Column | Current meaning | Example value | Migration impact |
|-------|--------|-----------------|---------------|------------------|
| `source_assets` | `storage_path` | Legacy relative path under v3_uploads | `uploads/aisles/{aisle}/raw/{id}_file.jpg` | Keep for legacy; new rows also populate provider fields |
| `source_assets` | `storage_provider` | `local` \| `s3` (future `gcs`) | `s3` | Add `gcs` enum value in app only |
| `source_assets` | `storage_bucket` | Bucket name when remote | `my-bucket` | Use GCS bucket name |
| `source_assets` | `storage_key` | Logical object key | `uploads/aisles/...` | **Canonical for remote** |
| `source_assets` | `content_type`, `file_size_bytes`, `etag` | Object metadata | | Already present |
| `evidences` | same pattern | Evidence artifact | | Same |
| `supplier_reference_images` | `storage_path` + provider fields | Supplier ref image | `client_suppliers/.../ref.jpg` | Same |
| `capture_session_items` | `staging_storage_key` | Staging object key only | session-relative key | Materialize → source_assets |
| `inventory_jobs` | `execution_log_storage_key`, `report_*_storage_key` | Durable worker outputs | `jobs/{id}/run/execution_log.jsonl` | Already keyed |
| `inventory_jobs` | `log_storage_provider`, `report_storage_provider` | Provider for job artifacts | | Extend for gcs |
| `inventory_visual_references` | (dropped) | Migration 0029 drops table if empty | N/A | Historical only |

### Schema adequacy

**No mandatory new columns** for a GCS migration if `storage_provider` accepts `gcs` and existing metadata columns are populated on write (already done by `put_object` for aisle uploads).

**Optional future columns** (not required for MVP):

- `checksum` / `sha256` — not present today; useful for backfill verification  
- `original_filename` — already on `source_assets.original_filename`  
- `created_at` — already on entities  

### Column usage patterns

| Pattern | Where |
|---------|--------|
| Filesystem relative path | `storage_path` always set on upload (even when provider set) |
| Logical key | `storage_key` when `put_object` used |
| Public URL in DB | **Not stored** (correct) |
| API path only | Frontend uses route URLs, not DB paths |

**Resolver rule** (`sql_storage_fields.resolved_storage_key_for_row`): When `storage_provider` is set, **only** `storage_key` is used — missing key does **not** fall back to `storage_path` (prevents silent wrong reads).

---

## 5. API impact

| Method | Endpoint | Current behavior | Returns local path? | Remote bucket impact |
|--------|----------|------------------|---------------------|----------------------|
| POST | `.../aisles/{aisle}/assets` | Multipart upload → ArtifactStore | No (returns asset DTO) | Uses configured provider |
| GET | `.../assets` | List metadata | `storage_path` in JSON — **relative key**, not OS path | OK if clients ignore for display |
| GET | `.../assets/{id}/file` | FileResponse or redirect | No | GCS: 307 presigned |
| GET | `.../assets/{id}/image-display-url` | JSON: `display_strategy`, `image_url`, `requires_authenticated_fetch` | No | **Primary FE contract** — add GCS signed URL |
| DELETE | `.../assets/{id}` | Delete object + DB row | No | `delete_object` on GCS |
| POST | `.../clients/.../reference-images` | Upload | No | Same adapter |
| GET | `.../reference-images/{id}/file` | Serve | No | Same |
| GET | `.../positions/...` | Evidence paths in DTO | `storage_path` field in schemas | Display via evidence endpoints |
| GET | Inventory/aisle exports | Stream CSV/zip | No | Unchanged |
| GET | Execution log / hybrid report | May stream from artifact store or aggregate | No | Reads via storage keys in job metadata |

**Frontend receives:** asset **IDs**, **display URLs** (presigned or API routes), occasionally **relative storage_path** in list DTOs (should not be used as `<img src>` directly).

---

## 6. Frontend impact

| Frontend area | File/module | Current assumption | Required change |
|---------------|-------------|-------------------|-----------------|
| Aisle upload | `api/assetsApi.ts`, `useAisleAssetUploadFlow` | Multipart to API | None if API unchanged |
| Image display | `fetchEvidenceImageDisplay`, `assetsApi.ts` | `image-display-url` then presigned or `/file` | **None** — GCS presigned URLs work like S3 |
| Evidence blob | `fetchAuthorizedReferenceFileAsBlob` | Bearer + `/file` | Fallback when no presigned URL |
| Supplier refs | `clientSuppliersApi.ts`, reference image modules | Similar file URL pattern | Verify same display-url pattern |
| Capture upload | `captureSessionsApi.ts` | XHR multipart | None |
| i18n errors | `errors.invalid_image_display_url` | | Keep |

### Least disruptive option

**Keep `GET .../image-display-url`** as the single display contract. Backend returns:

- `display_strategy: "presigned_url"` + `image_url: "https://storage.googleapis.com/..."` (short TTL), or  
- `display_strategy: "authenticated_file_fetch"` for local dev / fallback  

Do **not** expose `gs://` URIs or permanent public URLs to the browser.

---

## 7. Worker and pipeline impact

| Flow | Needs local file path? | Can use bytes? | Suggested migration strategy |
|------|------------------------:|---------------:|------------------------------|
| Aisle source asset input | **Yes** (today via download_to_path) | Partial | Download GCS object to **job temp dir** before OpenCV/video decode |
| Supplier reference images | **Yes** | Partial | Same |
| Frame extraction / ROI | **Yes** | No (OpenCV) | Ephemeral disk under `{output_dir}/{job_id}/run` remains |
| LLM multimodal | Bytes/base64 in adapters | Yes | Feed from downloaded temp or in-memory |
| Durable log/report publish | No (reads local temp, writes via put_object) | N/A | Already correct pattern |
| Hybrid report read (API) | No if metadata complete | get_object / redirect | Remove local file fallback after backfill |

**First flow to adapt:** aisle **source asset upload + display** (already uses `put_object` metadata). **Second:** supplier reference images. **Third:** worker **durable artifact** reads via storage keys only. **Fourth:** pipeline temp workspace policy (ephemeral volume sizing).

---

## 8. Existing abstraction opportunities

| Abstraction | Location | Role |
|-------------|----------|------|
| `ArtifactStore` | `infrastructure/storage/artifact_store.py` | **Canonical** — put/get/download/signed URL |
| `ArtifactStorage` | `application/ports/services.py` | Legacy port; extended by adapters |
| `V3ArtifactStorageAdapter` | local `v3_uploads` | Dev + legacy |
| `S3ArtifactStorageAdapter` | S3 + presigned | **Production pattern to copy for GCS** |
| `build_artifact_storage` | `runtime/container/storage_builders.py` | Provider switch |
| `DefaultStoredArtifactReader` | `infrastructure/artifacts/stored_artifact_reader.py` | JSON/log reads |
| `v3_stored_artifact_access` | API layer | FileResponse vs redirect |
| `WorkerInputArtifactResolver` | pipeline | Temp local materialization |
| `AisleSourceAssetMaterializer` | application | Single upload spine |
| `sql_storage_fields` | DB load rules | Key resolution |

**Recommendation:** **Extend** `ArtifactStorageSettings` + `build_artifact_storage` with `gcs` provider implementing **`ArtifactStore`** (not a separate parallel `StorageService`). Deprecate direct `save_file` over time in capture staging in favor of `put_object`.

**Duplicate / unused:** `src/storage/adapters/filesystem_artifact_storage.py` — do not wire GCS there; avoid third path.

---

## 9. Recommended target architecture

```text
Application (use cases, materializers, publisher)
        ↓
ArtifactStore port (put_object, get_object, download_to_path, generate_signed_url, delete_object)
        ↓
┌───────────────────┬────────────────────┬─────────────────────┐
│ V3ArtifactStorage │ S3ArtifactStorage  │ GcsArtifactStorage  │  ← new
│ Adapter (local)   │ Adapter (existing) │ Adapter (planned)   │
└─────────┬─────────┴──────────┬─────────┴──────────┬──────────┘
          ↓                      ↓                      ↓
   {OUTPUT_DIR}/v3_uploads   S3 bucket            GCS bucket (private)
          +
   {OUTPUT_DIR}/{job_id}/run/   ← ephemeral pipeline workspace (all providers)
```

### Recommended environment variables

Align with existing names; add GCS group:

```env
# Provider: local | s3 | gcs (gcs to be added)
ARTIFACT_STORAGE_PROVIDER=local

# Local (unchanged)
OUTPUT_DIR=output

# GCS (proposed — mirror S3 block)
GCS_BUCKET_NAME=
GCS_PROJECT_ID=
GCS_OBJECT_PREFIX=v3
GCS_SIGNED_URL_TTL_SECONDS=900

# Credentials (preferred for Docker/OpenCloud)
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-service-account.json

# Legacy migration (unchanged)
ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true

# Existing S3 block (keep if multi-cloud not needed)
ARTIFACT_S3_BUCKET=
ARTIFACT_S3_REGION=
ARTIFACT_S3_PREFIX=v3
ARTIFACT_S3_SIGNED_URL_TTL_SEC=900
```

**Deployment fit:** OpenCloud/Docker already uses **`env_file` + volume mounts** (`backend/docker-compose.yml`). **`GOOGLE_APPLICATION_CREDENTIALS`** as a mounted secret file is preferable to `GCS_CREDENTIALS_JSON` in `.env` (avoids leaking JSON in process listings and git).

---

## 10. Security recommendations

- GCS bucket must remain **private**; no public ACLs or `allUsers` access.  
- Frontend receives **time-limited signed URLs** or proxied authenticated responses — never permanent public object URLs.  
- Service account: **objectAdmin** scoped to the single bucket (or finer: create + read + delete on prefix).  
- Do **not** commit service account JSON; mount at runtime.  
- Do **not** log signed URLs, bearer tokens, or credential paths in production logs.  
- Validate **content-type** and **size** before `put_object` (already partially enforced).  
- Consider **checksum** on backfill for integrity verification.  
- CORS: configure bucket CORS only if browser will **fetch presigned URLs directly** (current FE pattern for S3 — same for GCS).  
- API middleware: optional `X-API-Key` remains separate from storage auth.

---

## 11. Migration strategy

### Phase 1 — Storage audit and abstraction boundary (complete / document)

- **Goal:** Map flows (this document).  
- **Files:** N/A (read-only).  
- **DoD:** Team agrees on `v3_uploads` vs job temp dirs.  
- **Tests:** N/A  

### Phase 2 — Local adapter parity (largely done)

- **Goal:** All durable writes go through `ArtifactStore`.  
- **Files:** `aisle_source_asset_materializer.py`, `upload_supplier_reference_images.py`, align `upload_capture_session_staging_items.py` to `put_object`.  
- **Risk:** Staging still uses `save_file` only.  
- **DoD:** No new direct writes to `v3_uploads` outside adapters.  
- **Tests:** `test_artifact_storage_config.py`, materializer tests  

### Phase 3 — GCS adapter

- **Goal:** `GcsArtifactStorageAdapter` implementing `ArtifactStore`.  
- **Files:** New `gcs_artifact_storage_adapter.py`, `storage_builders.py`, `grouped_settings.py`, `pyproject.toml` (`google-cloud-storage`).  
- **Risk:** Credential wiring in CI.  
- **DoD:** `ARTIFACT_STORAGE_PROVIDER=gcs` uploads and generates signed URLs in integration test (mock or emulator).  
- **Tests:** Adapter unit tests mirroring `test_s3_artifact_storage_adapter.py`  

### Phase 4 — API response migration

- **Goal:** Ensure all serve paths use `v3_stored_artifact_access` (GCS redirect).  
- **Files:** `assets.py`, `clients.py`, `v3_stored_artifact_access.py` (add `gcs` branch like `s3`).  
- **DoD:** FE displays images with GCS presigned URLs; no `storage_path` in new UI code paths.  
- **Tests:** `test_v3_stored_artifact_access_unit.py`, `test_heic_asset_preview.py`  

### Phase 5 — Worker/pipeline compatibility

- **Goal:** Worker downloads remote inputs to temp; publisher uploads durable outputs to GCS.  
- **Files:** `input_artifact_resolver.py`, `worker_durable_artifact_publisher.py`, `v3_job_executor.py` (disk quota).  
- **DoD:** End-to-end job on GCS-backed assets completes.  
- **Tests:** `test_v3_job_executor_input_resolution.py` with GCS mock  

### Phase 6 — Data migration / backfill

- **Goal:** Copy `output/v3_uploads/**` → GCS; update DB rows with `storage_provider=gcs`.  
- **Files:** New script `scripts/backfill_local_artifacts_to_gcs.py` (not implemented in audit).  
- **DoD:** Row count match; sample checksum audit.  
- **Rollback:** Keep local files until verified  

### Phase 7 — Cleanup and hardening

- **Goal:** Disable legacy local read in prod; GCS lifecycle rules; monitoring.  
- **Files:** Config docs, `DEV-OPENCLOUD.md`, bucket lifecycle JSON.  
- **DoD:** `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=false` in prod; no disk growth on API nodes for uploads  

---

## 12. Backward compatibility and rollback

### Read fallback order (recommended)

```text
1. If storage_provider == "gcs" (or "s3"): read via storage_key (+ bucket) from ArtifactStore.
2. Else if storage_provider == "local": read via storage_key under v3_uploads.
3. Else if legacy row (no provider): if ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED,
      read storage_path under v3_uploads.
4. Else: 404 StoredArtifactAccessError (incomplete_metadata / legacy_local_disabled).
```

### Rollback

- Set `ARTIFACT_STORAGE_PROVIDER=local`.  
- Re-enable `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true`.  
- Do not delete GCS objects or local files until dual-write period ends.  
- DB: additive columns only — no destructive migration required.

---

## 13. Testing strategy

| Test | Type | Notes |
|------|------|-------|
| Upload aisle asset local | integration | Existing |
| Upload aisle asset GCS | integration | Mock GCS client or test bucket |
| Signed URL generation | unit | TTL, key path |
| Expired signed URL | manual | Wait TTL |
| Worker processes GCS-backed asset | integration | download_to_path |
| FE `fetchEvidenceImageDisplay` | FE unit | `evidenceImageLoad.test.tsx` |
| Delete object | unit | idempotent |
| Missing object | API | 404 mapped |
| Invalid credentials | startup | fail-fast on container boot |
| Bucket unavailable | integration | graceful error |
| Large upload | API | `test_upload_file_limits_api.py` |
| Temp cleanup after worker | integration | job dir removed (policy) |
| Backfill script | manual | checksum sample |

---

## 14. Risks and open questions

| # | Question |
|---|----------|
| 1 | **S3 vs GCS in production:** Is AWS S3 already used in any environment, or is GCS the first remote provider? |
| 2 | **HEIC sidecars:** Normalized JPEG manifests stored beside assets on local disk — how to store on GCS (second object vs on-the-fly transform)? |
| 3 | **Pipeline disk:** What ephemeral volume size for `{output_dir}/{job_id}/run` on OpenCloud when inputs are HD video? |
| 4 | **Backfill strategy:** Big-bang vs lazy read-replicate on first access? |
| 5 | **Signed URL TTL:** 900s sufficient for long review sessions? Refresh strategy? |
| 6 | **CDN:** Needed in front of GCS for presigned GET? |
| 7 | **Lifecycle rules:** Per-prefix retention for `jobs/` vs `uploads/`? |
| 8 | **Capture staging `save_file`:** Unify on `put_object` before GCS cutover? |
| 9 | **Export package zip:** Does it write to `output/` temporarily? (validate `export_inventory_package`) |
| 10 | **Dual provider:** Need both S3 and GCS simultaneously, or one global `ARTIFACT_STORAGE_PROVIDER`? |

---

## 15. Final recommendation

### Safest implementation path

1. **Implement `GcsArtifactStorageAdapter`** parallel to S3 (same `ArtifactStore` methods + signed URL v4).  
2. **Wire `build_artifact_storage`** for `provider=gcs` + startup validation (bucket name, credentials file exists).  
3. **Extend `v3_stored_artifact_access`** with GCS redirect branch (copy S3 logic).  
4. **Unify capture staging** on `put_object`.  
5. **Run backfill** script with verification; then disable legacy local read in production.  
6. **Keep** ephemeral `{output_dir}/{job_id}/run` on worker/API disk — this is not replaced by GCS; only **durable** keys under `v3_uploads` / `jobs/` prefixes move to bucket.

### Do not implement yet

- Full removal of `OUTPUT_DIR` (pipeline still needs temp workspace).  
- Public bucket access.  
- Storing signed URLs in SQL.

### Acceptable short-term

- Local provider for dev/CI.  
- `storage_path` column populated alongside `storage_key` for traceability.  
- S3 adapter remains if another env uses AWS.

---

## Validation commands (executed / recommended)

```bash
# Repo scan (representative)
rg "output_dir|v3_uploads|ArtifactStorage|artifact_storage_provider" backend/src
rg "image-display-url|put_object|storage_key" backend/src frontend/src

# Config tests (safe)
pytest backend/tests/test_artifact_storage_config.py -q
pytest backend/tests/infrastructure/storage/test_s3_artifact_storage_adapter.py -q
pytest backend/tests/api/test_v3_stored_artifact_access_unit.py -q
```

---

*End of remote bucket storage readiness audit.*
