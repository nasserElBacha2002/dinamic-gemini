# PLAN V2.2 — User Stories and Technical Tasks

**Document version:** 1.1  
**Companion:** `docs/PLAN_V2.2_IMPLEMENTATION.md`  
**Stages:** 2.2.A (Flexible Input) → 2.2.B (FrameSource) → 2.2.C (Photo Normalization) → 2.2.D (LLM Provider) → 2.2.E (E2E Tests) → 2.2.F (Hard Cleanup).

**Current API contract (video, v2.1):** Create job is **multipart form**: `video` (File, required), `mode` (Form), `confidence_threshold` (Form), `metadata` (Form, optional). Video is saved under `output/<job_id>/input/<filename>`. No `video_path` in request body; path is produced server-side after upload.

**Photo normalization (2.2.C):** Normalization runs in the **worker/pipeline** (before the LLM call), not in the API request handler. The API (2.2.A) persists raw uploaded photos and manifest; the worker loads the job, runs normalization for photos jobs, then proceeds with FrameSource → LLM. This keeps the request handler fast and avoids long-running resize in the API process.

**FramesBundle contract:** `FramesBundle.frames` is **List[Path]** (paths to image files), not numpy arrays. Downstream (LLM provider, evidence pack) load from paths when needed.

---

# A) USER STORIES

---

## Stage 2.2.A — Flexible Input Endpoint (video | photos)

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-A1 | Create inventory job with video (unchanged) | Developer / Integrator | As an integrator, I can create an inventory job using the existing multipart form (video file + mode, confidence_threshold, metadata) so that existing integrations keep working. | **Given** a multipart POST with `video` (File) and no `input_type`, **when** I create job, **then** the server accepts it as video and returns 202 with `job_id`. **Given** `input_type=video` and the same multipart form, **then** same behavior. | Resizing, FrameSource, LLM provider | P0 |
| US-A2 | Create inventory job with multiple photos | Warehouse operator / Developer | As an operator, I can create an inventory job by submitting a set of photos (e.g. from a mobile app) so that I avoid uploading video and reduce cost. | **Given** a valid JSON body with `input_type=photos` and 1–N photos (filename + content_base64), **when** I POST, **then** the server returns 202 and persists photos under `run_dir/input_photos/` and writes `input_manifest.json`. **Given** N > MAX_PHOTOS_PER_JOB, **when** I POST, **then** the server returns 422 or 413. | Normalization (2.2.C) | P0 |
| US-A3 | Reject invalid photo payloads | Developer / Ops | As a developer, I need invalid photo payloads to be rejected with clear errors so that clients can correct requests. | **Given** invalid base64 in a photo item, **when** I POST photos job, **then** the server returns 422 with a message indicating invalid image content. **Given** total decoded bytes > PHOTOS_MAX_TOTAL_BYTES, **when** I POST, **then** the server returns 413 or 422. | — | P0 |
| US-A4 | Safe filenames for photos | Ops / Security | As an operator, I need photo filenames to be sanitized so that no path traversal or unsafe characters can write outside the job directory. | **Given** a photo with `filename` containing `../` or `\`, **when** the server persists it, **then** the stored file uses a safe canonical name (e.g. `0001_<slug>.jpg`) and is written only under `run_dir/input_photos/`. | — | P0 |
| US-A5 | Job record includes input metadata | Developer | As the worker, I need the job record to store `input_type` and paths (e.g. `input_manifest_path`, `photos_dir`) so that the pipeline can resolve input without the original request. | **Given** a created job (video or photos), **when** the worker loads the job, **then** it can determine input_type and paths to video or manifest/photos from the job record. | — | P1 |

---

## Stage 2.2.B — FrameSource Strategy

**FramesBundle:** `frames` is **List[Path]** (paths to image files on disk). Downstream (LLM provider, evidence pack) load from these paths when needed; no numpy arrays in the bundle.

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-B1 | Pipeline gets frames from strategy | Developer | As the pipeline, I obtain frames only via a FrameSource so that video and photos are handled uniformly. | **Given** a job with `input_type=video`, **when** the pipeline runs, **then** it uses VideoFrameSource and receives a FramesBundle. **Given** `input_type=photos`, **then** it uses PhotosFrameSource and receives a FramesBundle. No direct call to `extract_representative_frames` for all cases. | Normalization, LLM provider | P0 |
| US-B2 | Video path unchanged | Ops / QA | As an operator, I need video jobs to behave exactly as in v2.1 so that we do not regress. | **Given** the same video and config as v2.1, **when** the pipeline runs with VideoFrameSource, **then** the same frames (or equivalent selection) are used and the report/evidence match v2.1 behavior. | — | P0 |
| US-B3 | Photos frames in deterministic order | Developer | As the pipeline, I need photos to be supplied in a deterministic order (manifest index) so that entity ordering and IDs are stable. | **Given** a photos job with `input_manifest.json` listing N photos by index, **when** PhotosFrameSource.get_frames runs, **then** the returned frames list matches the manifest order (index 1..N). | — | P0 |
| US-B4 | Missing photo fails job clearly | Ops | As an operator, I need the job to fail with a clear error if a photo listed in the manifest is missing on disk. | **Given** the manifest lists a file that does not exist under run_dir, **when** PhotosFrameSource.get_frames runs, **then** the job fails with an explicit error (e.g. "missing input photo"). | — | P1 |

---

## Stage 2.2.C — Photo Normalization & Cost Optimization

**Where normalization runs:** In the **worker/pipeline**, before the LLM call (not in the API handler). Worker loads job → for photos, runs normalization → writes `input_photos/normalized/` and updates manifest → pipeline then uses FrameSource (which returns normalized paths).

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-C1 | Photos normalized before LLM | Ops / Cost | As an operator, I want uploaded photos to be resized and re-encoded so that LLM cost and latency are reduced. | **Given** a photos job with large images, **when** the worker runs normalization (before calling the LLM), **then** images are stored under `input_photos/normalized/` with max side ≤ PHOTO_RESIZE_MAX_SIDE and JPEG quality PHOTO_JPEG_QUALITY. **Given** a photos job, **when** the pipeline sends images to the LLM and builds evidence overview, **then** only normalized image paths (files under `input_photos/normalized/`) are used—never raw uploads. | Video logic | P0 |
| US-C2 | Manifest records normalization metrics | Developer / Ops | As an operator, I need the manifest to record original vs normalized bytes and dimensions for audit and analytics. | **Given** a photos job after normalization, **when** I read `input_manifest.json`, **then** each photo has original and normalized bytes/dims and a normalization config snapshot. | — | P1 |
| US-C3 | Optional keep originals | Ops | As an operator, I can enable keeping original photos for debugging, but by default only normalized are kept to save storage. | **Given** PHOTOS_KEEP_ORIGINALS=false (default), **when** photos are normalized, **then** only normalized files exist. **Given** PHOTOS_KEEP_ORIGINALS=true, **then** originals are under e.g. `input_photos/originals/`. | — | P2 |

---

## Stage 2.2.D — LLM Provider Strategy

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-D1 | Pipeline uses provider interface only | Developer | As the pipeline, I call only the LLM provider interface (e.g. analyze_global) so that we can swap providers without changing pipeline code. | **Given** the pipeline runs, **when** it needs LLM analysis, **then** it uses get_llm_provider(...).analyze_global(request) and does not import or call Gemini/OpenAI directly. | Multi-provider fallback | P0 |
| US-D2 | Gemini behavior unchanged | Ops / QA | As an operator, I need Gemini to behave exactly as in v2.1 when selected. | **Given** LLM_PROVIDER=gemini and the same inputs as v2.1, **when** the pipeline runs, **then** the report and evidence match v2.1 (same prompt, same schema, one call). | — | P0 |
| US-D3 | OpenAI provider available | Developer | As a developer, I can configure the OpenAI provider so that we can use it in the future without code changes. | **Given** OpenAI is configured and LLM_PROVIDER=openai, **when** the pipeline runs, **then** it uses OpenAI for multimodal analysis and returns JSON conforming to v2.1 schema. If not configured, clear error. | — | P1 |
| US-D4 | Errors normalized | Ops | As an operator, I need LLM errors (timeout, rate limit, invalid JSON) to be reported in a consistent way. | **Given** the provider raises (e.g. timeout), **when** the pipeline handles it, **then** it maps to a common error type (e.g. LLMProviderError) and fails the job with a clear status/message. | — | P1 |

---

## Stage 2.2.E — E2E Tests & Compatibility Validation

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-E1 | E2E video job (no regression) | Developer / QA | As a developer, I need an automated E2E test that runs a video job with a fake LLM and asserts report and evidence. | **Given** a video job created and run with FakeProvider, **when** the test runs, **then** hybrid_report.json, evidence_index.json, and evidence/ exist and entity list/report shape are valid. | Real Gemini in CI | P0 |
| US-E2 | E2E photos job | Developer / QA | As a developer, I need an E2E test for the full photos path. | **Given** a photos job (2–3 images) and FakeProvider, **when** the pipeline runs, **then** input_photos (and normalized), manifest, report, and evidence are generated. | — | P0 |
| US-E3 | Assisted counting API on photos job | Developer | As a developer, I need tests that verify entities, evidence, review, audit, and resolved report for a succeeded job. | **Given** a succeeded job with report and evidence, **when** the test calls GET entities, GET evidence, POST review, GET audit, GET report?resolved=true, **then** status codes and response shapes are correct and resolved report reflects the review. | — | P0 |
| US-E4 | Provider wiring verified | Developer | As a developer, I need a test that ensures the pipeline uses the provider from the factory (no direct Gemini in pipeline). | **Given** LLM_PROVIDER=fake, **when** the pipeline runs, **then** no network call is made and the report is produced from the fake response. | — | P1 |

---

## Stage 2.2.F — Hard Cleanup (remove legacy + dead code)

| ID | Title | Persona | Description | Acceptance Criteria | Out of scope | Priority |
|----|--------|---------|-------------|---------------------|--------------|----------|
| US-F1 | Legacy mode rejected at API | Integrator / Ops | As an integrator, I receive a clear error if I send mode=legacy so that I migrate to hybrid. | **Given** a create request with mode=legacy, **when** I POST, **then** the server returns 422 with a message that legacy was removed in v2.2. | — | P0 |
| US-F2 | No legacy code in runtime | Developer | As a developer, I want no legacy pipeline or report code in the codebase so that we maintain one path only. | **Given** the repo after 2.2.F, **when** I search for "legacy" in src/, **then** there are no productive code paths (only comments/changelog if needed). | — | P0 |
| US-F3 | Single hybrid flow | Developer | As the pipeline, I have one main flow (FrameSource → Provider → v2.1 steps) with no legacy branch. | **Given** the pipeline code, **when** I trace the execution, **then** there is no branch that invokes legacy pipeline or legacy report. | — | P1 |

---

# B) TECHNICAL TASKS

---

## Stage 2.2.A — Flexible Input Endpoint

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-A-00 | Add kill-switch config and enforce in API | `src/config.py`, `src/api/routes/jobs.py` | Add `ENABLE_PHOTOS_INPUT` (default true). In create endpoint: if `input_type=photos` and ENABLE_PHOTOS_INPUT is false, return 503 or 422 with message that photos input is disabled. | Unit test: config loads; API test: ENABLE_PHOTOS_INPUT=false and POST with input_type=photos → 503 or 422. | None | Low |
| V22-A-01 | Add config for photo limits | `src/config.py` | Add `MAX_PHOTOS_PER_JOB` (default 12), `PHOTOS_MAX_TOTAL_BYTES` (default 25*1024*1024). Validate ranges. | Unit test that config loads and respects env. | None | Low |
| V22-A-02 | Extend job input model | `src/jobs/models.py` | Add to JobInput (or equivalent): `input_type: str` ("video"\|"photos"), optional `input_manifest_path: str`, optional `photos_dir: str`. Keep `video_path` optional when input_type=photos. | Existing job (de)serialization tests. | None | Low |
| V22-A-03 | Photo filename sanitization helper | `src/utils/` or `src/io/sanitize.py`, `src/evidence/paths.py` | Reuse or extend slug(); canonical name `{index:04d}_{slug(filename)}.jpg`. Reject or strip `../`, `\`. | Unit: slug produces safe name; `../` stripped. | None | Low |
| V22-A-04 | Request schema for create (video + photos) | `src/api/schemas/requests.py` | Add body model(s): optional `input_type`; for photos: `photos: List[{ filename, content_base64 }]`. Validation: count, total size (after decode). | Schema validation tests. | V22-A-01 | Low |
| V22-A-05 | Create endpoint: accept video or photos | `src/api/routes/jobs.py` | If ENABLE_PHOTOS_INPUT is false and request has input_type=photos, reject with 503 or 422 (see V22-A-00). Branch on input_type (default video when multipart `video` file present). For photos: parse JSON body; validate count/size; decode base64; validate image (e.g. cv2.imdecode); sanitize filename; write to run_dir/input_photos/; write input_manifest.json. Create job with input_type, input_manifest_path, photos_dir. | API test: video unchanged (multipart form); API test: photos 202 + manifest; 422 invalid base64; 422/413 limits; ENABLE_PHOTOS_INPUT=false → photos rejected. | V22-A-00, V22-A-02, V22-A-03, V22-A-04 | Med |
| V22-A-06 | job_store.create_job accepts new fields | `src/jobs/job_store.py` | create_job(..., input_type=..., input_manifest_path=..., photos_dir=...) and persist in JobInput/record. | Test create then get_job has new fields. | V22-A-02 | Low |

---

## Stage 2.2.B — FrameSource Strategy

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-B-01 | Define FramesBundle and FrameSource protocol | `src/frames/types.py`, `src/frames/sources/base.py` | FramesBundle: frames (List[Path]), frame_refs (List[str]), metadata (dict: source, count, selected_by, ...). FrameSource.get_frames(job_id, run_dir, job_input) -> FramesBundle. | Unit: FramesBundle construction. | None | Low |
| V22-B-02 | Implement VideoFrameSource | `src/frames/sources/video_source.py` | Call existing extract_representative_frames(video_path); build FramesBundle from result (paths if persisted, else persist then paths); metadata.source="video". | Unit: mock extractor -> bundle with paths and metadata. | V22-B-01, existing `src/video/frames.py` | Med |
| V22-B-03 | Implement PhotosFrameSource | `src/frames/sources/photos_source.py` | Read run_dir/input_manifest.json; resolve paths (run_dir/input_photos/ or normalized/ per manifest); return bundle in index order; metadata.source="photos", selected_by="uploaded_photos". Raise if file missing. | Unit: manifest with 3 photos -> 3 paths in order; missing file -> error. | V22-B-01, V22-A-05 | Med |
| V22-B-04 | FrameSource factory | `src/frames/sources/factory.py` | get_frame_source(input_type: str) -> FrameSource. "video" -> VideoFrameSource(), "photos" -> PhotosFrameSource(). | Unit: factory returns correct type. | V22-B-02, V22-B-03 | Low |
| V22-B-05 | Pipeline uses FrameSource | `src/pipeline/hybrid_inventory_pipeline.py`, `src/jobs/worker.py` | In pipeline: get job_input (input_type, paths); frame_source = get_frame_source(job_input.input_type); bundle = frame_source.get_frames(job_id, run_dir, job_input); use bundle.frames and bundle.metadata for analyzer and evidence. Remove direct extract_representative_frames call. Worker passes run_dir and job input to pipeline. | Integration: video job -> same report shape; photos job (with manifest) -> report. | V22-B-04, V22-A-06 | High |
| V22-B-06 | Evidence pack accepts bundle | `src/evidence/evidence_pack.py` | Ensure generate_evidence_pack accepts frames as paths (or load from paths). No contract change; may need to load images from paths when needed for sharpness/crop. | Existing evidence tests; smoke with paths. | V22-B-05 | Low |

---

## Stage 2.2.C — Photo Normalization & Cost Optimization

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-C-01 | Config for normalization | `src/config.py` | PHOTO_RESIZE_MAX_SIDE (1280), PHOTO_JPEG_QUALITY (85), PHOTOS_KEEP_ORIGINALS (false), PHOTOS_MIN_SIDE (320 optional). | Config tests. | None | Low |
| V22-C-02 | Normalization module | `src/frames/normalize.py` | Pure functions: decode bytes -> image; resize if max(side) > max_side (aspect ratio); re-encode JPEG; return path, bytes, dims. Optional min_side check. | Unit: resize when over max_side; no resize when under; determinism. | V22-C-01 | Low |
| V22-C-03 | Persist normalized and extend manifest | `src/jobs/worker.py` and/or `src/pipeline/hybrid_inventory_pipeline.py` (invoke normalize before FrameSource); do not add normalization to API handler | After worker loads a photos job, run normalization (call normalize module); write to run_dir/input_photos/normalized/; optionally originals if KEEP. Update input_manifest.json with per-photo original/normalized metrics and normalization config. API (2.2.A) only persists raw photos; normalization runs in worker/pipeline before LLM. | Test: manifest has normalized paths and metrics. | V22-A-05, V22-C-02 | Med |
| V22-C-04 | PhotosFrameSource uses normalized paths | `src/frames/sources/photos_source.py` | Read stored_normalized_path (or equivalent) from manifest; resolve under run_dir. Return only normalized paths. | Unit: returns normalized paths; integration smoke. | V22-B-03, V22-C-03 | Low |

---

## Stage 2.2.D — LLM Provider Strategy

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-D-01 | LLM types and error | `src/llm/types.py`, `src/llm/errors.py` | LLMRequest (job_id, frames, prompt, schema_name, settings, metadata), LLMResponse (provider, model, latency_ms, parsed_json, usage), LLMSettings. LLMProviderError(code, message, details). | — | None | Low |
| V22-D-02 | LLMProvider protocol | `src/llm/providers/base.py` | Protocol: name, analyze_global(request) -> LLMResponse. | — | V22-D-01 | Low |
| V22-D-03 | GeminiProvider | `src/llm/providers/gemini_provider.py` | Wrap existing GeminiClient + GeminiGlobalAnalyzer: build payload from LLMRequest; call API; return LLMResponse(parsed_json=...). Same prompt and schema as today. | Unit: mock client -> response; integration: same output as v2.1. | V22-D-02, existing `src/llm/gemini_client.py`, `src/llm/gemini_global_analyzer.py` | High |
| V22-D-04 | OpenAIProvider | `src/llm/providers/openai_provider.py` | Implement analyze_global: multimodal request; return JSON in v2.1 shape. Raise LLMProviderError if not configured. | Unit: with mock/openai key returns dict; unconfigured -> error. | V22-D-02 | Med |
| V22-D-05 | FakeProvider | `src/llm/providers/fake_provider.py` | Returns fixed v2.1 JSON from fixture or in-memory. Optional: simulate timeout/invalid_json. | Unit: returns valid dict. | V22-D-02 | Low |
| V22-D-06 | Provider factory | `src/llm/providers/factory.py`, `src/config.py` | get_llm_provider(provider_name, config). Config LLM_PROVIDER (default gemini). Map gemini|openai|fake to implementation. | Unit: factory returns correct type. | V22-D-03, V22-D-04, V22-D-05 | Low |
| V22-D-07 | Pipeline uses provider only | `src/pipeline/hybrid_inventory_pipeline.py` | Build LLMRequest from FramesBundle and job metadata; provider = get_llm_provider(config); response = provider.analyze_global(request); use response.parsed_json for validate_v21 -> parse_entities -> ... Remove direct Gemini imports from pipeline. | Integration: FakeProvider -> report; no Gemini import in pipeline. | V22-B-05, V22-D-06 | High |

---

## Stage 2.2.E — E2E Tests & Compatibility Validation

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-E-01 | Fixtures for v2.1 JSON and photos | `tests/fixtures/v2_1/global_analysis_ok.json`, `tests/fixtures/v2_1/global_analysis_unlocalized.json`, `tests/fixtures/photos/` | Valid v2.1 global analysis (2 pallets, 1 conflict, etc.); unlocalized (no bboxes); 2–3 small synthetic images (numpy or files). | — | None | Low |
| V22-E-02 | E2E video job | `tests/test_e2e_v2_2.py` or similar | Create video job; run pipeline with FakeProvider returning fixture; assert hybrid_report.json, evidence_index.json, evidence/; assert entity list. | test_e2e_video_job_generates_report_and_evidence | V22-D-07, V22-E-01 | Med |
| V22-E-03 | E2E photos job | Same file | Create photos job (fixture images); run pipeline with FakeProvider; assert input_photos, manifest, report, evidence. **Assert:** LLM and evidence overview receive only image paths under `input_photos/normalized/` (no raw upload paths). | test_e2e_photos_job_persists_and_generates_report; assertion that only normalized paths are passed to LLM and evidence. | V22-C-04, V22-E-01 | Med |
| V22-E-04 | E2E evidence LOCALIZED vs UNLOCALIZED | Same file | Run with bbox vs no-bbox fixture; assert evidence_localization and label crops presence. | test_e2e_evidence_localization_modes | V22-E-01 | Low |
| V22-E-05 | E2E assisted counting API | Same file | Succeeded job; GET entities, GET evidence, POST review, GET audit, GET report?resolved=true; assert status and body; resolved has COUNTED_MANUAL. | test_api_review_flow_photos_job or video | V22-E-02 or V22-E-03 | Low |
| V22-E-06 | Pipeline uses provider factory (no network) | Same file | LLM_PROVIDER=fake; run pipeline; assert no network; assert request metadata. | test_pipeline_uses_llm_provider_strategy | V22-D-07 | Low |

---

## Stage 2.2.F — Hard Cleanup

| Task ID | Description | Files impacted | Implementation notes | Tests to add/update | Dependencies | Risk |
|---------|-------------|----------------|----------------------|---------------------|--------------|------|
| V22-F-01 | Reject mode=legacy at API | `src/api/routes/jobs.py` | If mode==legacy, return 422 with message "legacy mode has been removed in v2.2". | test_create_job_rejects_legacy_mode | None | Low |
| V22-F-02 | Remove legacy branch from pipeline | `src/pipeline/hybrid_inventory_pipeline.py` | Remove `if mode == "legacy"` and LegacyVisualPipeline usage; keep only hybrid path (FrameSource + Provider). | All pipeline tests must use hybrid. | V22-D-07 | High |
| V22-F-03 | Delete legacy modules | `src/pipeline/legacy_visual_pipeline.py`, any legacy-only modules | Delete files; fix imports elsewhere. | Remove legacy tests; ensure no imports. | V22-F-02 | Med |
| V22-F-04 | Remove legacy config and tests | `src/config.py`, tests | Remove legacy-related config; delete or update tests that referenced legacy. | CI green | V22-F-03 | Low |
| V22-F-05 | Consolidate utilities | `src/utils/validation.py`, path/slug helpers, dedupe if duplicated | Single place for job_id/entity_uid validation; single place for slug/paths; remove duplicates. | Existing validation/path tests | None | Low |

---

# PR Plan (recommended grouping)

| PR | Scope | Tasks | Notes |
|----|--------|--------|--------|
| PR-2.2.A | Flexible input endpoint | V22-A-00 through V22-A-06 | Kill-switch (ENABLE_PHOTOS_INPUT), config, model, schema, route, store; tests for video (multipart) + photos. |
| PR-2.2.B | FrameSource strategy | V22-B-01 through V22-B-06 | New frames package; pipeline wiring; evidence compatible. |
| PR-2.2.C | Photo normalization | V22-C-01 through V22-C-04 | Config, normalize module, persist normalized, PhotosFrameSource uses normalized. |
| PR-2.2.D | LLM provider strategy | V22-D-01 through V22-D-07 | Types, protocol, Gemini/OpenAI/Fake, factory, pipeline refactor. |
| PR-2.2.E | E2E and compatibility | V22-E-01 through V22-E-06 | Fixtures, E2E tests for video, photos, evidence, API, provider. |
| PR-2.2.F | Hard cleanup | V22-F-01 through V22-F-05 | Reject legacy, remove legacy code, consolidate utils. |

---

# Definition of Done for the Whole Release

- [ ] All stages A–F implemented and merged; CI green.
- [ ] Video path: create → run → report + evidence + entities/review unchanged vs v2.1.
- [ ] Photos path: create with N photos → run → input_photos (normalized), input_manifest.json, report, evidence; entities and review API work.
- [ ] Invalid photo payloads (bad base64, invalid image, excess count/size, unsafe filename) return 422/413 with clear detail.
- [ ] Pipeline uses only FrameSource and LLMProvider interface; no direct Gemini/OpenAI in pipeline.
- [ ] Legacy mode rejected (422); no legacy runtime code in tree.
- [ ] job_id and entity_uid validation (path-safe) applied; photo filenames sanitized.
- [ ] E2E tests for video and photos; assisted counting flow covered; FakeProvider used in CI (no network).
- [ ] Photos jobs: assertion or test that only normalized images (paths under `input_photos/normalized/`) are passed to the LLM and to evidence overview.
- [ ] ENABLE_PHOTOS_INPUT kill-switch: when false, photos input rejected at API.
- [ ] Docs/README updated (video + photos input, new config, legacy removal).

---

# Rollback Strategy

**If the photos path causes production issues:**

1. **Immediate:** Set `ENABLE_PHOTOS_INPUT=false` (kill-switch added in 2.2.A). API rejects `input_type=photos` with 503 or 422 ("photos input is disabled"). No code deploy needed if config is env-based. Video path and existing jobs continue to work.
2. **Short-term:** Revert the PR(s) that introduced photos (2.2.A, and optionally 2.2.B/2.2.C if they are only used for photos). Video path and FrameSource/Provider refactors can stay if they are backward compatible (video still works).
3. **Data:** No schema rollback needed for existing jobs. New jobs created with photos would have run_dir/input_photos and manifest; if we revert, those jobs may be left in a failed or incomplete state; document that photos jobs may need to be re-submitted after fix.
4. **Communication:** Release notes should state that photos input can be disabled via config; operators should not rely on photos until E2E and staging validation are complete.

**If the LLM provider refactor causes regressions:**

1. Keep `LLM_PROVIDER=gemini` as default; ensure GeminiProvider is a thin wrapper so behavior is identical. If issues appear, fix in GeminiProvider without reverting the whole strategy.
2. If necessary, revert only the pipeline change that calls the provider (reintroduce direct Gemini call) while keeping the provider modules for future use; this is a last resort and should be avoided by thorough testing with FakeProvider and one real Gemini run in staging.
