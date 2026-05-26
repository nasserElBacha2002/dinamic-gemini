# GCS artifact storage adapter — Phase 1 implementation report

## 1. Executive summary

**Status:** `IMPLEMENTED`

Phase 1 adds Google Cloud Storage as a third `ArtifactStore` provider (`gcs`) alongside existing `local` and `s3` modes. New durable uploads can target a private GCS bucket; API serving uses signed GET URLs (307 redirect / `image-display-url`) matching the S3 pattern. No backfill, no removal of local `output`, no frontend contract changes.

## 2. What changed

| File | Why |
|------|-----|
| `backend/src/infrastructure/storage/gcs_artifact_storage_adapter.py` | New GCS `ArtifactStore` implementation |
| `backend/src/env_settings/grouped_settings.py` | Provider `gcs`, GCS env fields, validation |
| `backend/src/runtime/container/storage_builders.py` | Wire `GcsArtifactStorageAdapter` when provider=gcs |
| `backend/src/api/services/v3_stored_artifact_access.py` | GCS signed URL + 307 redirect for file/image display |
| `backend/src/infrastructure/artifacts/stored_artifact_reader.py` | `gcs` requires bucket in provider metadata |
| `backend/src/api/server.py` | Startup log for GCS artifact config |
| `backend/tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py` | Mocked GCS client unit tests |
| `backend/tests/test_artifact_storage_config.py` | GCS provider validation + builder wiring tests |
| `backend/tests/api/test_v3_stored_artifact_access_unit.py` | GCS redirect / image-display-url tests |
| `backend/requirements.txt`, `backend/pyproject.toml` | `google-cloud-storage` dependency |
| `.env.example` | Document GCS env vars |
| `docs/deployment/GCS-ARTIFACT-STORAGE.md` | Operator deployment notes |

## 3. Configuration added

| Env var | Settings field | Default | Required when `gcs` |
|---------|----------------|---------|---------------------|
| `ARTIFACT_STORAGE_PROVIDER` | `artifact_storage_provider` | `local` | Set to `gcs` |
| `GCS_BUCKET_NAME` | `artifact_gcs_bucket` | `""` | **Yes** |
| `GCS_PROJECT_ID` | `artifact_gcs_project_id` | `""` | No |
| `GCS_OBJECT_PREFIX` | `artifact_gcs_prefix` | `v3` | No |
| `GCS_SIGNED_URL_TTL_SECONDS` | `artifact_gcs_signed_url_ttl_sec` | `900` | No |
| `GOOGLE_APPLICATION_CREDENTIALS` | `google_application_credentials` | `""` | No (validated if set: file must exist) |

Valid providers: `local`, `s3`, `gcs`.

## 4. Runtime behavior

| `ARTIFACT_STORAGE_PROVIDER` | Behavior |
|-----------------------------|----------|
| `local` | Unchanged: `V3ArtifactStorageAdapter` under `{OUTPUT_DIR}/v3_uploads` |
| `s3` | Unchanged: `S3ArtifactStorageAdapter`, presigned GET URLs |
| `gcs` | New: `GcsArtifactStorageAdapter`, v4 signed GET URLs, DB metadata `storage_provider=gcs` |

## 5. API behavior

- **`GET .../file`**: For rows with `storage_provider=gcs`, returns **307** to a time-limited signed GCS URL (same as S3).
- **`GET .../image-display-url`**: Returns signed URL with `display_strategy=presigned_url` for GCS-backed non-HEIC assets.
- **Legacy rows**: Unchanged when `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true`.
- No `gs://` or permanent public URLs exposed.

## 6. Tests run

| Command | Result |
|---------|--------|
| `pytest tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py tests/infrastructure/storage/test_s3_artifact_storage_adapter.py -q --noconftest --no-cov` | **10 passed** |
| `pytest tests/test_artifact_storage_config.py tests/api/test_v3_stored_artifact_access_unit.py -q` | **Not run in agent environment** (system Python 3.9; project requires 3.11+). Run in project venv/CI. |

Recommended CI/local:

```bash
pytest backend/tests/test_artifact_storage_config.py -q
pytest backend/tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py -q
pytest backend/tests/api/test_v3_stored_artifact_access_unit.py -q
ruff check backend/src backend/tests
```

## 7. Limitations

This phase does **not**:

- Backfill existing local files to GCS
- Remove or shrink `output/` usage
- Remove pipeline temp disk under `{OUTPUT_DIR}/{job_id}/run/`
- Create/configure the GCS bucket or service account in GCP
- Add CDN or lifecycle rules

Signed URL generation requires credentials with sign capability (service account JSON via `GOOGLE_APPLICATION_CREDENTIALS` is the expected production path).

## 8. Next recommended phase

**Phase 2 — Align capture session staging and remaining durable local writes behind `put_object`**

Ensure any code paths that still write directly under `v3_uploads` use `ArtifactStore.put_object` when `ARTIFACT_STORAGE_PROVIDER=gcs`, then run production deploy configuration and a manual smoke test with a private bucket.
