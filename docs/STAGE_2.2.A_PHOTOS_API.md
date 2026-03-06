# Stage 2.2.A — Photos create-job API

Same endpoint as video: `POST /api/v1/inventory/jobs`. **Video** and **photos** both use **multipart/form-data**.

## Request (photos)

- **Content-Type:** `multipart/form-data`
- **Form fields:**
  - `input_type` = `photos` (required for photos job)
  - `photos` = **multiple files** (same field name; at least one image file)
  - `mode` = `hybrid` (required; `legacy` is rejected for photos)
  - `confidence_threshold` = `0.7` (optional)
  - `metadata` = JSON string (optional)

- **Validation:** 1 ≤ number of photos ≤ `MAX_PHOTOS_PER_JOB` (default 12); total bytes ≤ `PHOTOS_MAX_TOTAL_BYTES` (default 25 MB); each file must be a valid image (e.g. JPEG); filenames are sanitized server-side.
- **Kill-switch:** If `ENABLE_PHOTOS_INPUT=false`, requests with `input_type=photos` return **422**.

## Example (curl)

```bash
curl -s -X POST http://localhost:8000/api/v1/inventory/jobs \
  -F "input_type=photos" \
  -F "mode=hybrid" \
  -F "photos=@/path/to/image1.jpg" \
  -F "photos=@/path/to/image2.jpg"
```

## Postman

1. Method: **POST**, URL: `http://localhost:8000/api/v1/inventory/jobs`
2. Body → **form-data**
3. Add keys: `input_type` (Text) = `photos`, `mode` (Text) = `hybrid`
4. Add key `photos`, type **File**, and select one image; then add another row with key `photos` again and another file (repeat for more photos)
5. Send

## Response

Same as video: **202** with `job_id`, `status`, `mode`, `confidence_threshold`. Photos are stored under `output/<job_id>/run/input_photos/` as `0001_<slug>.jpg`, `0002_<slug>.jpg`, etc. Manifest: `output/<job_id>/run/input_manifest.json`.
