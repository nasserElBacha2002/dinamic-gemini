# Bug Investigation: PROCESSING_FAILED / Pipeline exited with code 1

## Symptom

- Job ends with `error_code: PROCESSING_FAILED` and `error_message: Pipeline exited with code 1`.
- API response only shows this generic message; the underlying exception is not exposed to the client.

## Expected Behavior

- On pipeline failure, the job/aisle should record a **specific** cause (e.g. "manifest not found", "No frames could be loaded", "decoded bytes are not a valid image", LLM/permission/disk error) so operators can fix the issue without digging through logs.

## Area(s) Suspect (Platform / Pipeline)

- **Platform:** Error handling in the worker and v3 job executor (generic message stored; real exception only logged).
- **Pipeline:** All stages that return exit code 1: InputPreparation, FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting. Input/photo handling and unsupported image formats (e.g. HEIC) are high probability.

## Hypotheses (ranked)

### H1: Unsupported image format (e.g. HEIC) — decode fails, pipeline returns 1

- **Why likely:** Your job output folder contains `input_manifest.json` with `.heic` files. The stack uses `cv2.imdecode` (normalize) and `cv2.imread` (frame load). OpenCV does **not** support HEIC; decode returns `None` / raises, leading to `ValueError` or "No frames could be loaded" and exit code 1.
- **How to confirm:** Check worker/pipeline logs for the job_id for one of: `"decoded bytes are not a valid image"`, `"Photo normalization failed"`, `"No frames could be loaded from bundle"`, or `"Stage failure: InputPreparationStage"` / `"Stage failure: FrameAcquisitionStage"`.
- **Logs/metrics to add:** In `HybridInventoryPipeline._run_hybrid`, when a stage raises, log `job_id`, stage name, and `repr(e)` at ERROR; optionally append last stage error to a small file in `run_dir` (e.g. `run_dir / "last_stage_error.txt"`) so executor can read and store it.
- **Minimal repro:** Run a v3 process_aisle job with a single HEIC asset; expect code 1 and the log messages above.
- **Fix (minimal):** (1) Reject HEIC (or unsupported formats) at upload/validation with a clear 4xx and message, or (2) add server-side HEIC→JPEG conversion (e.g. pillow-heif or external tool) before normalize/analysis so the pipeline only sees JPEG/PNG.

### H2: Manifest or photos path wrong for v3 photos jobs

- **Why likely:** InputPreparationStage and PhotosFrameSource resolve manifest/photos from `run_dir` and `job_input`. If `run_dir.parent` (job_dir) or relative paths don’t match where the executor wrote the manifest/photos, we get `FileNotFoundError("manifest not found: ...")` or "photos directory not found" and exit 1.
- **How to confirm:** In logs, search for `"manifest not found"` or `"photos directory not found"` or `"photos input manifest not found"` for the failing job_id. Inspect `resolve_manifest_path` / `resolve_photos_dir` vs actual paths (executor writes `job_dir/input_manifest.json`, `job_dir/input_photos`).
- **Logs/metrics to add:** In InputPreparationStage (photos branch), log at INFO: `manifest_path`, `photos_dir`, and `manifest_path.exists()`, `photos_dir.is_dir()`.
- **Minimal repro:** Run v3 process_aisle with photos; ensure executor and pipeline use the same `base_path` and that no other process deletes `job_dir/input_manifest.json` before the pipeline runs.
- **Fix (minimal):** Ensure worker and executor use the same `base_path`; add a single place that defines job_dir/run_dir layout and use it in both executor and pipeline; if manifest is ever written elsewhere (e.g. upload handler), align path resolution with that.

### H3: Pipeline stage exception (Analysis / EntityResolution / Evidence / Reporting)

- **Why likely:** LLM timeout/quota, malformed response (GlobalAnalysisParseError), or disk/permission on evidence or report write can cause a stage to raise; pipeline catches and returns 1.
- **How to confirm:** Logs will show `"Stage failure: AnalysisStage"`, `"EntityResolutionStage"`, `"EvidenceStage"`, or `"ReportingStage"` with the exception message.
- **Logs/metrics to add:** Same as H1: per-stage exception logging with job_id and stage name; optional `last_stage_error.txt` in run_dir.
- **Minimal repro:** Depends on stage (e.g. mock LLM error, read-only run_dir for ReportingStage).
- **Fix (minimal):** Fix underlying cause (retry/backoff for LLM, validation for parser, disk space/permissions). For reporting, ensure `run_dir` is writable and `write_json`/`write_report_csv` errors are logged with path and errno.

### H4: Persist step raises after pipeline succeeds (would not show "Pipeline exited with code 1")

- **Why unlikely for this symptom:** If `_persist_use_case.execute` raised, the executor’s `except Exception` would run and `_fail_job_and_aisle(job_id, aisle, str(e))` would set `error_message` to the **actual** exception (e.g. DB constraint, report key missing). The user would **not** see "Pipeline exited with code 1".
- **How to confirm:** If `error_message` is exactly "Pipeline exited with code 1", the failure happened in the pipeline (code != 0), not in persist.
- **Logs/metrics to add:** Already present in PersistAisleResultUseCase (logger.exception on save failure).
- **Fix (minimal):** N/A for this symptom; if persist failures are seen with a different error_message, fix mapping/DB/constraints.

### H5: Result/detail contract changes (removing `products` from API response) caused pipeline failure

- **Why unlikely:** Contract changes were limited to **API response** (PositionDetailResponse) and **frontend types/mapper**. The pipeline does not build that response. Persist still writes positions, product_records, and evidences via `map_hybrid_report_to_domain`; no pipeline stage or executor code was changed to stop producing or writing `products`. Pipeline exit code 1 is determined only by the staged run (input → frames → analysis → resolution → evidence → reporting).
- **How to confirm:** Grep for `products` in `src/pipeline`, `src/infrastructure/pipeline`, `src/reporting`; no pipeline logic depends on the detail response shape. Persist and v3_report_mapper still create and save ProductRecord.
- **Fix (minimal):** None for this symptom.

## Most Likely Root Cause

**H1 (unsupported image format, especially HEIC)** is the most probable when the failing job’s manifest lists `.heic` (or other non-OpenCV formats). Decode fails in normalization or frame load, pipeline returns 1, and the executor only stores the generic "Pipeline exited with code 1".

**H2 (path/manifest)** is next if the same failure occurs with JPEG/PNG and paths differ between executor and pipeline (e.g. base_path, or manifest written in a different layout).

## Proposed Fix Plan (ordered)

1. **Immediate: Improve observability**
   - In `src/infrastructure/pipeline/v3_job_executor.py`, when `code != 0`, try to read a small `run_dir / "last_stage_error.txt"` if present and append its content (or first line) to the stored `error_message` so the API exposes a hint (e.g. "Pipeline exited with code 1: decoded bytes are not a valid image").
   - In `src/pipeline/hybrid_inventory_pipeline.py`, in each `except` block that returns 1, write a one-liner to `context.run_dir / "last_stage_error.txt"` (stage name + `repr(e)`), and ensure `logger.exception` is called so logs have the full traceback.

2. **Root cause: Input format**
   - If HEIC (or similar) is in use: either reject at upload with a clear error, or add HEIC→JPEG conversion before the pipeline (so normalize and frame load only see supported formats).

3. **Path robustness**
   - Add the INFO logs in InputPreparationStage (manifest_path, photos_dir, exists/is_dir) for photos jobs to quickly confirm path alignment in production.

4. **Optional: Persist errors**
   - If in the future persist failures should be distinguished from pipeline failures, set a distinct `error_code` (e.g. `PERSIST_FAILED`) when the exception is raised after `code == 0` and report_path.exists().

## Regression Prevention (tests + invariants)

- **Unit test:** For a photos job with a mock HEIC (or invalid image bytes), assert pipeline returns 1 and (if implemented) `last_stage_error.txt` contains the expected substring (e.g. "decoded" or "not a valid image").
- **Integration test:** v3 process_aisle with one JPEG photo succeeds; with one .heic (or unsupported) file, job fails and stored error_message (or last_stage_error) contains a recognizable reason (format/decode/frames).
- **Invariant:** Any pipeline exit code != 0 should result in a stored error_message that includes either the generic "Pipeline exited with code N" plus a hint (from last_stage_error.txt) or, when we refactor, the actual exception message.

## Debug Checklist (runbook)

1. Get `job_id` and (if v3) `aisle_id` from the failed job/aisle.
2. Locate logs for that `job_id` (worker and pipeline log to `job_dir` when available). Search for:
   - `"Stage failure:`
   - `"manifest not found"`, `"photos directory not found"`, `"photos input manifest not found"`
   - `"decoded bytes are not a valid image"`, `"Photo normalization failed"`
   - `"No frames could be loaded"`
   - `"Pipeline exited with code"`
3. If logs are missing, check `output_dir / job_id / run / last_stage_error.txt` (once implemented).
4. Inspect `output_dir / job_id / input_manifest.json`: if `stored_filename` ends with `.heic`, treat H1 as confirmed and add format validation or HEIC conversion.
5. For path issues: list `output_dir / job_id` and `output_dir / job_id / run`; confirm `input_manifest.json` and `input_photos/` exist before the run (and that base_path in worker matches the API’s upload/job directory).
6. If failure is in Analysis/EntityResolution, check LLM quota, timeouts, and response shape; for Evidence/Reporting, check disk space and permissions on `run_dir`.

---

## Exact files/functions to inspect first

| Area | File | Function / location |
|------|------|----------------------|
| Where PROCESSING_FAILED is set | `src/infrastructure/pipeline/v3_job_executor.py` | `_fail_job_and_aisle` (error_code="PROCESSING_FAILED"); call site when `code != 0` (lines 129–133) |
| Where "Pipeline exited with code N" is set | `src/infrastructure/pipeline/v3_job_executor.py` | `execute()`, branch `if code != 0` |
| Pipeline exit code 1 | `src/pipeline/hybrid_inventory_pipeline.py` | `_run_hybrid`: all `except ... return 1` (InputPreparation, FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting) |
| Photo normalization (decode) | `src/frames/normalize.py` | `normalize_photo_to_file` → `decode_image_bytes`; `normalize_photos_for_job` (manifest not found, decode error) |
| Frame load (imread) | `src/pipeline/stages/frame_acquisition_stage.py` | `run`: `cv2.imread(str(p))`; "No frames could be loaded" |
| Manifest/photos resolution | `src/pipeline/stages/input_preparation_stage.py` | photos branch: manifest_path, photos_dir from run_dir.parent + relative |
| Photos frame source | `src/frames/sources/photos_source.py` | `get_frames`: manifest_path.exists(), photos_dir, stored_filename / stored_normalized_filename |
| Path helpers | `src/jobs/photos_paths.py` | `resolve_manifest_path`, `resolve_photos_dir` (run_dir.parent + relative) |
| Persist (not cause of "code 1") | `src/application/use_cases/persist_aisle_result.py` | `execute`; `src/infrastructure/pipeline/v3_report_mapper.py` (still maps products) |
