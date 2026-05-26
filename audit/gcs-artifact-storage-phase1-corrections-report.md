# GCS artifact storage — Phase 1 corrections report

## 1. Executive summary

**Status:** `CORRECTIONS_IMPLEMENTED_WITH_LIMITATIONS`

All code-review corrections (A1–A4) are applied and covered by new/updated unit tests for the GCS adapter. Full backend validation (`test_artifact_storage_config`, `test_v3_stored_artifact_access_unit`) could not be executed in the agent environment because only Python 3.9 was available; the project requires **Python 3.11+**. No real GCS bucket smoke test was performed.

## 2. Corrections applied

| Correction | Status | Files changed | Notes |
| ---------- | ------ | ------------- | ----- |
| A1 — `file_size_bytes` uses full stream length | Done | `gcs_artifact_storage_adapter.py`, `test_gcs_artifact_storage_adapter.py` | `stream_size = int(end)` after seek-to-EOF; prefer `blob.size` after `reload()` |
| A2 — Idempotent `delete_object` on missing object | Done | `gcs_artifact_storage_adapter.py`, `test_gcs_artifact_storage_adapter.py` | Catches `google.api_core.exceptions.NotFound` only |
| A3 — Align `google-cloud-storage` versions | Done | `requirements.txt` | `google-cloud-storage>=2.14.0` (matches `pyproject.toml`) |
| A4 — Rename bucket validation helper | Done | `stored_artifact_reader.py`, `v3_stored_artifact_access.py` | `ensure_remote_bucket_matches_configured` |
| A5 — Update Phase 1 implementation report | Done | `gcs-artifact-storage-adapter-implementation-report.md` | Status and validation notes updated |

## 3. Tests added

| Test | Protects against |
| ---- | ---------------- |
| `test_gcs_adapter_put_object_records_full_size_when_stream_cursor_at_eof` | `file_size_bytes=0` when upload uses `rewind=True` but cursor was at EOF |
| `test_gcs_adapter_delete_object_is_idempotent_for_missing_object` | Cleanup/retry flows crashing on already-deleted GCS objects |

Fake GCS blob `delete()` now raises `NotFound` when the object is absent (matching SDK behavior).

## 4. Validation commands

| Command | Result |
| ------- | ------ |
| `pytest tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py -q --no-cov --noconftest` | **6 passed** (Python 3.9, with `google-cloud-storage` installed) |
| `pytest tests/test_artifact_storage_config.py -q` | **Not run** — requires Python 3.11+ (import fails on 3.9) |
| `pytest tests/api/test_v3_stored_artifact_access_unit.py -q` | **Not run** — requires Python 3.11+ (api conftest) |
| `python -m compileall backend/src` | **Partial** — targeted compile of changed modules OK |
| `ruff check` (changed files) | **Pass** |

Recommended in project venv (Python 3.11+):

```bash
cd backend
pytest tests/test_artifact_storage_config.py -q
pytest tests/infrastructure/storage/test_gcs_artifact_storage_adapter.py -q
pytest tests/api/test_v3_stored_artifact_access_unit.py -q
python -m compileall src
ruff check src tests
```

## 5. Remaining limitations

- **Backfill** — not implemented.
- **`output/`** — still used for local provider, legacy reads, and pipeline ephemeral workspace.
- **Pipeline temp disk** — unchanged; GCS objects are downloaded to temp paths when needed.
- **Real GCS smoke test** — not performed; no production bucket or service account was exercised.
- **GCS credentials** — not validated against a live bucket in this correction pass.

## 6. Recommended next phase

**Phase 2 — Production GCS configuration and real bucket smoke test**

Configure production-like env vars, mount `GOOGLE_APPLICATION_CREDENTIALS`, upload one test asset, verify DB metadata (`storage_provider=gcs`, bucket, key, size, etag), confirm `image-display-url` and `GET .../file` (307 → signed URL), and confirm the bucket stays private.

---

## Roadmap (Phases 2–7 — documentation only)

### Phase 2 — Production GCS configuration and real bucket smoke test

Validate startup, upload, DB metadata, signed URL display, 307 redirect, private bucket, credentials not committed.

### Phase 3 — Audit and align remaining durable local writes

Search for direct `v3_uploads` / durable filesystem writes; route durable uploads through `ArtifactStore.put_object`.

### Phase 4 — Worker and pipeline remote-read compatibility

Download GCS-backed assets to controlled temp paths for OpenCV/Pillow; cleanup temp files; avoid redundant downloads per job.

### Phase 5 — API contract hardening for image display

Provider-agnostic frontend contract; consistent errors for missing objects, bucket mismatch, incomplete metadata.

### Phase 6 — Backfill existing local artifacts to GCS

Dry-run/write/verify script with `--limit`, `--resume`, rollback documentation; do not delete local files in this phase.

### Phase 7 — Cleanup, lifecycle rules, and production hardening

GCS lifecycle by prefix, monitoring, CI guard against new durable local writes, disable legacy reads only after verified backfill.
