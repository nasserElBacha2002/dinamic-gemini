# GCS artifact storage (Phase 1)

Durable v3 uploads (source assets, visual references, worker-published JSON) can use a **private** Google Cloud Storage bucket via the existing `ArtifactStore` abstraction. Local and S3 providers remain supported.

## Required environment variables

```env
ARTIFACT_STORAGE_PROVIDER=gcs
GCS_BUCKET_NAME=your-private-bucket
GCS_PROJECT_ID=your-gcp-project-id
GCS_OBJECT_PREFIX=v3
GCS_SIGNED_URL_TTL_SECONDS=900
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-service-account.json
```

- `GCS_BUCKET_NAME` is **required** when `ARTIFACT_STORAGE_PROVIDER=gcs`.
- `GCS_OBJECT_PREFIX` defaults to `v3`.
- `GCS_SIGNED_URL_TTL_SECONDS` defaults to `900`.
- `GOOGLE_APPLICATION_CREDENTIALS` is the preferred credentials mechanism (Application Default Credentials). The file must exist at startup when set. **Never commit** the service account JSON.
- **Docker:** place the key at `secrets/gcp-service-account.json` in the repo root; `backend/docker-compose.yml` mounts it read-only at `/app/secrets/`. See `secrets/README.md`.

## Security

- Keep the bucket **private**; do not enable public access or permanent public object URLs.
- Enable **Public Access Prevention** on the bucket.
- Signed URLs are generated at request time and are **not** stored in the database.

## Runtime notes

- `OUTPUT_DIR` is still required for pipeline ephemeral workspace (`{output_dir}/{job_id}/run/`).
- Legacy rows without provider metadata can still be read from local `v3_uploads` when `ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED=true`.
- This phase does **not** backfill existing local files to GCS.

## API behavior

Existing endpoints are unchanged:

- `GET .../assets/{id}/file` → `307` redirect to a signed GCS GET URL for GCS-backed rows.
- `GET .../assets/{id}/image-display-url` → returns the signed URL with `display_strategy=presigned_url`.
