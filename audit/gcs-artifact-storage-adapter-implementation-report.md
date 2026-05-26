# GCS artifact storage adapter — Phase 1 implementation report

## 1. Executive summary

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`

Phase 1 adds Google Cloud Storage as a third `ArtifactStore` provider (`gcs`) alongside existing `local` and `s3` modes. Code-review corrections (size calculation, idempotent delete, dependency alignment, helper rename) are applied. GCS adapter unit tests pass; full config/API suites require Python 3.11+ in the project venv. No real bucket smoke test yet.

## 2. What changed

| File | Why |
|------|-----|
| `backend/src/infrastructure/storage/gcs_artifact_storage_adapter.py` | GCS `ArtifactStore` + Phase 1 corrections |
| `backend/src/env_settings/grouped_settings.py` | Provider `gcs`, GCS env fields, validation |
| `backend/src/runtime/container/storage_builders.py` | Wire `GcsArtifactStorageAdapter` when provider=gcs |
| `backend/src/api/services/v3_stored_artifact_access.py` | GCS signed URL + 307 redirect |
| `backend/src/infrastructure/artifacts/stored_artifact_reader.py` | `gcs` bucket metadata; `ensure_remote_bucket_matches_configured` |
| `backend/src/api/server.py` | Startup log for GCS artifact config |
| `backend/tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py` | Mocked GCS client unit tests (incl. EOF size + idempotent delete) |
| `backend/tests/test_artifact_storage_config.py` | GCS provider validation + builder wiring tests |
| `backend/tests/api/test_v3_stored_artifact_access_unit.py` | GCS redirect / image-display-url tests |
| `backend/requirements.txt`, `backend/pyproject.toml` | `google-cloud-storage>=2.14.0` |
| `.env.example`, `docs/deployment/GCS-ARTIFACT-STORAGE.md` | Operator docs |
| `audit/gcs-artifact-storage-phase1-corrections-report.md` | Corrections + roadmap |

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
| `gcs` | `GcsArtifactStorageAdapter`, v4 signed GET URLs, DB metadata `storage_provider=gcs` |

## 5. API behavior

- **`GET .../file`**: GCS rows → **307** to signed GET URL.
- **`GET .../image-display-url`**: Signed URL with `display_strategy=presigned_url`.
- **Legacy rows**: Unchanged when `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true`.

## 6. Tests run

| Command | Result |
|---------|--------|
| `pytest tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py -q --noconftest --no-cov` | **6 passed** (agent env, Python 3.9 + `google-cloud-storage` installed) |
| `pytest tests/test_artifact_storage_config.py -q` | **Not run** — Python 3.11+ required |
| `pytest tests/api/test_v3_stored_artifact_access_unit.py -q` | **Not run** — Python 3.11+ required |
| `ruff check` (changed files) | **Pass** |

Run in project venv before production deploy.

## 7. Limitations

- No backfill of existing local files
- `output/` still required for pipeline temp and legacy/local modes
- No real GCS bucket smoke test in Phase 1 or corrections pass
- Signed URLs require credentials with sign capability

## 8. Next recommended phase

**Phase 2 — Production GCS configuration and real bucket smoke test** (see `audit/gcs-artifact-storage-phase1-corrections-report.md` for full roadmap).
