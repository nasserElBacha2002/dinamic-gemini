# PLAN V2.2 IMPLEMENTATION

**Document version:** 1.0  
**Source of truth:** `docs/V.2.2.md`  
**Current baseline:** v2.1 (hybrid inventory, single LLM call, evidence pack, assisted counting API, video-only input).

---

## Executive Summary

Version 2.2 extends the inventory system to support **two input modes** (video and photo set) while keeping the v2.1 pipeline, report schema, evidence pack, and assisted counting API unchanged. The release is structured in six stages:

| Stage | Focus | Outcome |
|-------|--------|--------|
| **2.2.A** | Flexible input endpoint | API accepts `input_type=video` or `input_type=photos`; validation and persistence (input_manifest, input_photos). |
| **2.2.B** | FrameSource strategy | Pipeline consumes a unified `FramesBundle` from `VideoFrameSource` or `PhotosFrameSource`. |
| **2.2.C** | Photo normalization | Resize/re-encode for photos; enforce limits; normalized artifacts for LLM. |
| **2.2.D** | LLM provider strategy | Pipeline depends on `LLMProvider` interface; Gemini + OpenAI implementations; single call per job. |
| **2.2.E** | E2E and compatibility tests | Offline integration tests for video/photos, evidence, assisted counting, provider wiring. |
| **2.2.F** | Hard cleanup | Remove legacy mode and unused code; simplify pipeline. |

**Principles:** Backward compatibility for video; deterministic entity ordering unchanged; one LLM call per job; no direct provider calls in pipeline; minimal refactor of v2.1 logic.

---

## Architecture Impact Overview

- **Input layer:** One create endpoint supports both video (current behavior) and photos (new). Job record and run_dir gain `input_type`, optional `photos_dir` / `input_manifest_path`.
- **Frame acquisition:** Abstracted behind `FrameSource`; pipeline no longer calls `extract_representative_frames` directly for all cases.
- **LLM layer:** Abstracted behind `LLMProvider`; pipeline calls `provider.analyze_global(request)` instead of Gemini client directly.
- **Downstream:** Entity parsing, ordering, count_status, evidence pack, report, review API remain as in v2.1. They consume frames (paths or arrays) and LLM JSON; no schema or contract changes.

---

## New Components Diagram (Text)

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                   CREATE JOB API                          │
                    │  input_type: "video" | "photos"                          │
                    │  video → save to input/; photos → run_dir/input_photos/   │
                    │  write input_manifest.json                               │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
                                                ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │                   WORKER                                 │
                    │  load job → run_dir, job_input (input_type, paths)       │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
                                                ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │              FrameSource (Strategy)                     │
                    │  get_frame_source(input_type) → Video | Photos          │
                    │  .get_frames(job_id, run_dir, job_input) → FramesBundle │
                    │  FramesBundle: frames (paths), frame_refs, metadata     │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
                    ┌───────────────────────────┴─────────────────────────────┐
                    │  VideoFrameSource          │  PhotosFrameSource          │
                    │  extract_representative_   │  read input_manifest +      │
                    │  frames(video_path)       │  input_photos/normalized/   │
                    └───────────────────────────┴─────────────────────────────┘
                                                │
                                                ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │              LLM Provider (Strategy)                     │
                    │  get_llm_provider(config) → Gemini | OpenAI | Fake      │
                    │  .analyze_global(LLMRequest) → LLMResponse (parsed_json) │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
                                                ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │              v2.1 PIPELINE (unchanged)                  │
                    │  validate_v21 → parse_entities → sort → resolve_id →   │
                    │  assign_count_status → quality_score → evidence_pack →  │
                    │  build_hybrid_report → write report + evidence_index    │
                    └─────────────────────────────────────────────────────────┘
```

---

## Data Flow Changes

| Step | v2.1 | v2.2 |
|------|------|------|
| Job creation | Video file → `input/<video>.mp4` | Video **or** photos → video path **or** `run_dir/input_photos/` + `input_manifest.json` |
| Frames for LLM | `extract_representative_frames(video_path)` | `frame_source.get_frames(...)` → `FramesBundle.frames` (paths) |
| LLM call | `GeminiGlobalAnalyzer.analyze_video_frames(...)` | `provider.analyze_global(LLMRequest)` → `LLMResponse.parsed_json` |
| After LLM | Same: parse → sort → resolve → status → evidence → report | Same |

---

## Configuration Changes

| Config / env | Default | Stage | Purpose |
|--------------|---------|-------|---------|
| `MAX_PHOTOS_PER_JOB` | 12 | A, C | Max number of photos per job. |
| `PHOTOS_MAX_TOTAL_BYTES` | 25 * 1024 * 1024 | A, C | Max total bytes for photo set. |
| `PHOTO_RESIZE_MAX_SIDE` | 1280 | C | Max side after resize (photos). |
| `PHOTO_JPEG_QUALITY` | 85 | C | JPEG quality for normalized photos. |
| `PHOTOS_KEEP_ORIGINALS` | false | C | Keep originals in `input_photos/originals/`. |
| `PHOTOS_MIN_SIDE` | 320 | C | (Optional) Reject images smaller than this. |
| `LLM_PROVIDER` | `gemini` | D | Provider name: `gemini` \| `openai` \| `fake`. |
| (Existing) | — | — | `hybrid_max_frames`, `output_dir`, evidence_*, etc. unchanged. |

---

## API Contract Changes

### POST create job (2.2.A)

**Backward compatibility:** If `input_type` is omitted and a video file is provided (current form/multipart), treat as `input_type=video`. No change for existing clients.

**Request — Video (existing):** Form/multipart: `video` (file), `mode` (e.g. `hybrid`), `confidence_threshold`, optional `metadata`. Optional: `input_type=video`.

**Response (unchanged):** `202` — `{ "job_id": "job_xxx", "status": "queued", "mode": "hybrid", "confidence_threshold": 0.7 }`.

**Request — Photos (new):** JSON body example:
```json
{
  "input_type": "photos",
  "photos": [
    { "filename": "img_001.jpg", "content_base64": "<base64>" },
    { "filename": "img_002.jpg", "content_base64": "<base64>" }
  ],
  "mode": "hybrid",
  "confidence_threshold": 0.7
}
```
Validation: `1 <= len(photos) <= MAX_PHOTOS_PER_JOB`; total decoded bytes `<= PHOTOS_MAX_TOTAL_BYTES`; each item: `filename` (non-empty), `content_base64` (valid decode + minimal image check). Filenames sanitized (no `../`, `\`).

**Response:** Same `202` with `job_id`, `status`, `mode`. **Errors:** Invalid payload → `422`; excess count/size → `413` or `422`; invalid base64/image → `422`.

### Other endpoints

**GET** `/{job_id}/result`, **GET** `/{job_id}/report`, **GET** `/{job_id}/entities`, **GET** `/{job_id}/entities/{entity_uid}/evidence`, **POST** `.../review`, **GET** `.../audit`: request/response shapes unchanged. `job_id` and `entity_uid` remain validated via existing `src/utils/validation.py`.

---

## Security Considerations

- **job_id / entity_uid validation:** Existing validation in `src/utils/validation.py` (allowed pattern `^[a-zA-Z0-9_-]+$`; reject `..`, `/`, `\`) must remain applied in `src/jobs/job_store.py` and `src/api/routes/jobs.py`, `src/api/routes/entities.py`. No new path parameters that bypass this.
- **Path safety (photos):** Sanitize photo `filename` (no `../`, `\`); use slug/canonical names (e.g. `0001_<slug>.jpg`) under `run_dir/input_photos/` only. Reuse or extend `src/evidence/paths.py` slug and write only under the job’s `run_dir`.
- **Size limits:** Enforce `MAX_PHOTOS_PER_JOB` and `PHOTOS_MAX_TOTAL_BYTES` before writing to disk to avoid DoS and disk exhaustion.
- **No new path parameters** that could introduce traversal; keep validation centralized.

---

## Performance Considerations

- **Photos:** Normalization (decode → resize → re-encode) runs once at job creation or at frame-source read; pipeline and LLM receive normalized paths only. N and total bytes are capped by config.
- **Video:** Unchanged; no extra I/O.
- **LLM:** Single call per job preserved; provider layer adds minimal overhead (request/response wrapping).

---

## Migration Strategy from v2.1

- **No data migration:** Existing jobs and reports remain valid. New fields (`input_type`, `input_manifest_path`, etc.) are additive on job record and manifest.
- **Deployment:** Deploy with feature behind existing API; video-only clients unchanged. Enable photos when ready.
- **Rollback:** If needed, disable photos path (e.g. reject `input_type=photos` with 501) and keep video path; no schema rollback required.

---

## Release Validation Checklist

- [ ] Video job: create → run → report + evidence + entities/review unchanged vs v2.1.
- [ ] Photos job: create with 2–3 images → run → report + evidence; `input_manifest.json` and `input_photos/normalized/` present.
- [ ] GET entities, evidence, POST review, GET audit, GET report?resolved=true work for a photos job.
- [ ] Invalid photo payload (bad base64, excess count/size, bad filename) → 422/413 with clear message.
- [ ] `LLM_PROVIDER=fake` runs pipeline without network; tests green.
- [ ] Legacy mode removed (2.2.F); API rejects `mode=legacy` with 422.
- [ ] CI: all E2E and unit tests pass; no new linter/type errors.

---

# Stage 2.2.A — Flexible Input Endpoint

## Objective

Extend the **same** create-inventory endpoint to accept either **video** or **photos**, with strict validation and persistence. No pipeline or strategy changes yet; only contracts, validation, and storage of input.

## Scope

**In scope**

- Request schema supports `input_type = "video"` \| `"photos"`.
- Validation: video path required for video; photos array required for photos; count and total size limits; base64 decode and minimal image check; filename sanitization.
- Persistence: for photos, write under `run_dir/input_photos/` with canonical names; write `run_dir/input_manifest.json` for both video and photos.
- Job record extended with `input_type`, optional `photos_dir` / `input_manifest_path`.
- Backward compatibility: if `input_type` is omitted and only video is provided, treat as video.

**Out of scope**

- Resizing/optimization (2.2.C).
- FrameSource or pipeline changes (2.2.B).
- LLM provider abstraction (2.2.D).

## Architectural Changes

- API: one endpoint, two input shapes (video upload vs photos payload).
- Job creation creates `run_dir` early for photos and writes `input_manifest.json` there; worker will read it later.
- Job input model: add `input_type`; for photos, store manifest path and/or photos_dir instead of only `video_path`.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Modify | `src/api/routes/jobs.py` — accept video **or** photos; validate; persist photos and manifest. |
| Modify | `src/api/schemas/requests.py` — add request body model(s) for create (video vs photos). |
| Modify | `src/jobs/models.py` — extend `JobInput` (or equivalent) with `input_type`, optional `input_manifest_path`, `photos_dir`. |
| Modify | `src/jobs/job_store.py` — `create_job` accepts new fields; no change to get/update semantics. |
| Modify | `src/config.py` — add `MAX_PHOTOS_PER_JOB`, `PHOTOS_MAX_TOTAL_BYTES`. |
| Create | Helper for photo validation and safe filename (e.g. in `src/utils/` or `src/io/sanitize.py`). |

## Key Implementation Tasks

1. Add config: `MAX_PHOTOS_PER_JOB` (e.g. 12), `PHOTOS_MAX_TOTAL_BYTES` (e.g. 25 MiB).
2. Define request contract: `input_type` optional; if missing and video present → video. For photos: `photos: [{ filename, content_base64 }]`; validate count, total size, decode, and minimal image check (e.g. cv2.imdecode or PIL).
3. Sanitize filenames: no `../`, `\`; canonical stored name `0001_<slug>.jpg` (reuse or align with `evidence/paths.py` slug).
4. On create (photos): create `run_dir` and `run_dir/input_photos/`; write decoded images; write `run_dir/input_manifest.json` with index, original_filename, stored_filename, bytes per photo, total_photos, total_bytes.
5. On create (video): keep current behavior; optionally write a minimal `input_manifest.json` with `input_type: "video"`, `video_path`.
6. Extend job record (DB/FS): store `input_type`, `input_manifest_path`, and for photos `photos_dir` (or equivalent) so worker can resolve input without re-reading request body.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing video clients | Keep video as default when `input_type` absent; do not require new fields for video. |
| Path traversal via filename | Strict slug/sanitization; write only under `run_dir/input_photos/`. |
| Large payload / DoS | Enforce `PHOTOS_MAX_TOTAL_BYTES` and `MAX_PHOTOS_PER_JOB` before writing. |
| Invalid image content | Validate decode; reject with 422 and clear message. |

## Acceptance Criteria (Definition of Done)

- Endpoint accepts video as today when no `input_type` or `input_type=video`.
- Endpoint accepts photos when `input_type=photos` with validation (count, size, base64, image validity, filename sanitization).
- For photos: `run_dir/input_photos/` and `run_dir/input_manifest.json` exist; manifest matches contract (index, filenames, bytes).
- Job record contains `input_type` and, for photos, paths needed for worker (manifest/photos_dir).
- Invalid payloads (bad base64, invalid image, excess count/size, unsafe filename) return 422 or 413 with clear detail.
- No change to v2.1 entity/report/evidence/review logic.

## Testing Strategy

- **Backward compatibility:** Request without `input_type` but with video file → accepted as video; job runs as today.
- **Photos happy path:** 2 small base64 images → job created; `input_photos/` and `input_manifest.json` present and valid.
- **Photos invalid base64** → 422.
- **Photos invalid image bytes** → 422.
- **Limits:** `len(photos) > MAX_PHOTOS_PER_JOB` → reject; `total_bytes > PHOTOS_MAX_TOTAL_BYTES` → reject.
- **Filename sanitization:** filename containing `../` → stored with safe name; no write outside `run_dir`.

---

# Stage 2.2.B — FrameSource Strategy

## Objective

Introduce an explicit abstraction for obtaining “frames” (images fed to analysis) so the pipeline is agnostic to video vs photos. The pipeline consumes a single `FramesBundle` produced by a `FrameSource` implementation.

## Scope

**In scope**

- Define `FramesBundle` (frames as paths, frame_refs, metadata) and `FrameSource` protocol/interface.
- Implement `VideoFrameSource` (wraps current `extract_representative_frames`; returns bundle).
- Implement `PhotosFrameSource` (reads `input_manifest.json` and `input_photos/`; returns bundle in deterministic order).
- Factory: `get_frame_source(input_type) → FrameSource`.
- Pipeline: replace direct frame extraction with “get frame_source → get_frames → use bundle”; rest of pipeline unchanged.

**Out of scope**

- Normalization of photos (2.2.C).
- LLM provider abstraction (2.2.D).
- Changes to evidence pack contract (only ensure it can consume bundle).

## Architectural Changes

- New package `src/frames/`: types (`FramesBundle`), sources (base, video, photos), factory.
- Pipeline has a single frame-acquisition point: `frame_source.get_frames(job_id, run_dir, job_input)` → `FramesBundle`; then use `bundle.frames` (paths) and `bundle.metadata` for LLM and evidence.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Create | `src/frames/types.py` — `FramesBundle` (frames, frame_refs, metadata). |
| Create | `src/frames/sources/base.py` — `FrameSource` protocol. |
| Create | `src/frames/sources/video_source.py` — `VideoFrameSource` using `extract_representative_frames`. |
| Create | `src/frames/sources/photos_source.py` — `PhotosFrameSource` from manifest + input_photos. |
| Create | `src/frames/sources/factory.py` — `get_frame_source(input_type)`. |
| Modify | `src/pipeline/hybrid_inventory_pipeline.py` — obtain frames only via FrameSource; pass bundle into LLM and evidence. |
| Modify | `src/jobs/worker.py` — pass `input_type` and run_dir to pipeline so it can resolve frame source. |

## Key Implementation Tasks

1. Define `FramesBundle`: `frames: List[Path]` (or list of paths as strings), `frame_refs: List[str]`, `metadata: dict` (source, count, selected_by, input_manifest_path when photos).
2. Implement `VideoFrameSource.get_frames`: call `extract_representative_frames(video_path)`; build bundle from result (paths if already persisted, or persist then paths); metadata.source = `"video"`.
3. Implement `PhotosFrameSource.get_frames`: read `run_dir/input_manifest.json`; resolve paths from manifest (e.g. `run_dir/input_photos/0001_xxx.jpg`); return bundle in index order; metadata.source = `"photos"`, selected_by = `"uploaded_photos"`. If a listed file is missing, raise clear error.
4. Factory: map `"video"` → VideoFrameSource, `"photos"` → PhotosFrameSource.
5. In pipeline: get `job_input` (including `input_type`); `frame_source = get_frame_source(job_input.input_type)`; `bundle = frame_source.get_frames(job_id=..., run_dir=..., job_input=...)`; use `bundle.frames` and `bundle.metadata` for analyzer and evidence. Replace direct `extract_representative_frames` call with this.
6. Evidence pack: ensure it accepts frames as paths (or arrays loaded from paths); use existing logic; no contract change.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Video behavior change | VideoFrameSource must return same frames and ordering as current extractor; test with same video. |
| Photos order non-deterministic | Order by manifest `index` only; do not rely on filesystem order. |
| Missing photo file | Validate all manifest entries exist on disk; fail job with clear error. |

## Acceptance Criteria (Definition of Done)

- `FrameSource` interface and two implementations exist; factory selects by `input_type`.
- Pipeline obtains frames only via factory + `get_frames`; no scattered `if video/photos` in pipeline.
- Video path behavior unchanged (same selection and results as v2.1).
- Photos path yields deterministic `frames` and `frame_refs` from manifest order.
- Evidence pack and report work with both sources; no change to report/evidence schema.
- Unit tests: PhotosFrameSource ordering and missing file; VideoFrameSource returns expected shape; pipeline smoke test with fake or photos source.

## Testing Strategy

- Unit: PhotosFrameSource with manifest of 3 photos → bundle has 3 paths in order; missing file → error.
- Unit: VideoFrameSource (mock extractor) → bundle with paths and metadata.source = `"video"`.
- Integration: Create photos job with manifest; run pipeline with mock LLM; assert report generated and frames_selected matches photo count.

---

# Stage 2.2.C — Photo Normalization and Cost Optimization

## Objective

Normalize uploaded photos (decode, optional resize, re-encode to JPEG) and enforce size/count limits so that the LLM and evidence pack consume a single set of normalized artifacts, reducing cost and latency while keeping behavior deterministic and auditable.

## Scope

**In scope**

- Normalization: decode → validate min dimensions (optional) → resize if max side > config → re-encode JPEG with config quality.
- Persist normalized images under `run_dir/input_photos/normalized/`; optionally keep originals under `run_dir/input_photos/originals/` if `PHOTOS_KEEP_ORIGINALS=true`.
- Extend `input_manifest.json` with per-photo and global metrics (original vs normalized bytes/dims, resize flag) and normalization config snapshot.
- PhotosFrameSource returns **normalized** paths only.
- Enforce `MAX_PHOTOS_PER_JOB` and `PHOTOS_MAX_TOTAL_BYTES` (consolidate with 2.2.A if needed).

**Out of scope**

- Changes to v2.1 entity/report schema.
- LLM provider strategy (2.2.D).
- Normalization for video (video path unchanged).

## Architectural Changes

- Normalization can live in a dedicated module (e.g. `src/frames/normalize.py`) used when persisting photos (2.2.A) or when PhotosFrameSource first runs (2.2.B). Preferred: normalize at persistence time (2.2.A) so run_dir always contains normalized assets; PhotosFrameSource just reads them.
- If normalization runs in 2.2.C after 2.2.A: add a normalization step (e.g. after writing raw photos) that produces `normalized/` and updates manifest; PhotosFrameSource then reads from `normalized/` only.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Create | `src/frames/normalize.py` — pure functions: decode, resize (aspect ratio), re-encode; return paths and metrics. |
| Modify | `src/config.py` — add `PHOTO_RESIZE_MAX_SIDE`, `PHOTO_JPEG_QUALITY`, `PHOTOS_KEEP_ORIGINALS`, optional `PHOTOS_MIN_SIDE`. |
| Modify | Job creation (photos) or worker/pipeline entry — after saving raw photos, run normalization and write to `input_photos/normalized/`; update `input_manifest.json` with extended schema (original/normalized per photo, totals, normalization config). |
| Modify | `src/frames/sources/photos_source.py` — read frame paths from manifest `stored_normalized_path` (or equivalent) under `run_dir`; ensure only normalized paths are returned. |

## Key Implementation Tasks

1. Add config: `PHOTO_RESIZE_MAX_SIDE`, `PHOTO_JPEG_QUALITY`, `PHOTOS_KEEP_ORIGINALS`, `PHOTOS_MIN_SIDE` (optional).
2. Implement normalization: for each photo, decode; check min side if configured; resize if max(w,h) > PHOTO_RESIZE_MAX_SIDE (preserve aspect); encode to JPEG with PHOTO_JPEG_QUALITY; write to `normalized/<canonical>.jpg`; record bytes and dimensions before/after.
3. Extend manifest: each photo has `original` (bytes, w, h), `normalized` (bytes, w, h), `stored_normalized_path`, `resized`; root has `total_bytes_original`, `total_bytes_normalized`, `normalization: { resize_max_side, jpeg_quality, keep_originals }`.
4. Enforce limits before or during normalization: total bytes and count; reject with 413/422 if exceeded.
5. PhotosFrameSource: use only normalized paths from manifest; no reference to raw upload paths for LLM/evidence.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Label detail lost by resize | Make `PHOTO_RESIZE_MAX_SIDE` configurable; document for small labels. |
| CPU overhead | Normalize only for photos; N and size capped. |
| Storage growth | Default `PHOTOS_KEEP_ORIGINALS=false`. |

## Acceptance Criteria (Definition of Done)

- For `input_type=photos`, system stores and uses **normalized** images; LLM and evidence consume normalized paths only.
- Limits applied: count and total bytes; manifest includes original vs normalized metrics and config snapshot.
- Video path unchanged (no regression).
- Unit tests: resize when over max_side; no resize when under; determinism; limit rejection.

## Testing Strategy

- Unit: image 4000×3000, max_side=1280 → normalized dimensions correct.
- Unit: image 1024×768 → no resize but re-encoded; deterministic path.
- Unit: total_bytes or count over limit → reject.
- Smoke: photos job with 2 images → PhotosFrameSource returns normalized paths; evidence pack runs without error.

---

# Stage 2.2.D — LLM Provider Strategy

## Objective

Decouple the pipeline from the concrete LLM (Gemini) by introducing a provider interface and factory. The pipeline calls a single method (e.g. `analyze_global`) and receives a normalized response; Gemini and OpenAI are implementations behind config or override.

## Scope

**In scope**

- Define `LLMProvider` protocol/interface and normalized types (`LLMRequest`, `LLMResponse`, settings).
- Implement `GeminiProvider` wrapping existing Gemini client/analyzer; same behavior as v2.1.
- Implement `OpenAIProvider` for multimodal JSON analysis (operational but not necessarily default).
- Factory: `get_llm_provider(provider_name, config)`.
- Pipeline refactor: build `LLMRequest` from job_id, frames (paths), prompt, schema info, settings, metadata; call `provider.analyze_global(request)`; use `response.parsed_json` for validate_v21 → parse_entities → …; no direct Gemini import in pipeline.
- Common error type (e.g. `LLMProviderError`) for timeout, rate_limit, invalid_json, etc.

**Out of scope**

- Multi-provider fallback.
- Prompt or schema changes.
- Extra LLM calls (still one per job).

## Architectural Changes

- New types in `src/llm/types.py`; protocol in `src/llm/providers/base.py`; implementations in `src/llm/providers/gemini_provider.py`, `openai_provider.py`; factory in `src/llm/providers/factory.py`; errors in `src/llm/errors.py`.
- Pipeline and worker: no direct use of `GeminiClient` / `GeminiGlobalAnalyzer`; they use `get_llm_provider(...).analyze_global(request)`.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Create | `src/llm/types.py` — LLMRequest, LLMResponse, LLMSettings. |
| Create | `src/llm/providers/base.py` — LLMProvider protocol. |
| Create | `src/llm/providers/gemini_provider.py` — wrap existing Gemini logic. |
| Create | `src/llm/providers/openai_provider.py` — OpenAI multimodal + JSON. |
| Create | `src/llm/providers/factory.py` — get_llm_provider. |
| Create | `src/llm/providers/fake_provider.py` — for tests; returns fixed v2.1 JSON. |
| Create | `src/llm/errors.py` — LLMProviderError. |
| Modify | `src/pipeline/hybrid_inventory_pipeline.py` — build request; call provider; use response.parsed_json; remove direct Gemini dependency. |
| Modify | `src/config.py` — add `LLM_PROVIDER` (default `gemini`). |

## Key Implementation Tasks

1. Define `LLMRequest` (job_id, frames, prompt, schema_name/schema, settings, metadata), `LLMResponse` (provider, model, latency_ms, parsed_json, usage), `LLMSettings` (timeout, max_retries, etc.).
2. Implement GeminiProvider: adapt current `GeminiGlobalAnalyzer` (or client) to accept LLMRequest, build payload, call API, return LLMResponse(parsed_json=...). Keep prompt and parsing behavior identical.
3. Implement OpenAIProvider: build multimodal request; return JSON in v2.1 shape; raise LLMProviderError if not configured.
4. Factory: from config (and optional request override with allowlist) return provider instance.
5. Pipeline: create LLMRequest from FramesBundle and job metadata; get provider from factory; call analyze_global; on success use response.parsed_json for existing validate/parse flow; on error map to LLMProviderError and fail job with clear status.
6. FakeProvider: return fixture JSON for tests; optionally simulate errors.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| JSON format differs per provider | Contract: parsed_json must pass validate_global_analysis_structure_v21; validate after call. |
| OpenAI API changes | Isolate in openai_provider.py; tests with FakeProvider for CI. |

## Acceptance Criteria (Definition of Done)

- Pipeline depends only on LLMProvider and factory; no direct Gemini/OpenAI imports in pipeline.
- Gemini behavior identical to v2.1 (regression zero).
- OpenAIProvider implemented and callable when configured.
- Errors normalized to LLMProviderError; pipeline and API can map to 502/503 and logging.
- Tests: factory selection; pipeline uses provider interface (FakeProvider); no extra LLM call.

## Testing Strategy

- Unit: get_llm_provider("gemini"|"openai"|"fake") returns correct type.
- Unit/integration: pipeline with FakeProvider returns report from fixture JSON; validate_v21 passes.
- Error: FakeProvider raises invalid_json → pipeline fails job with clear error.

---

# Stage 2.2.E — End-to-End Tests and Compatibility Validation

## Objective

Add offline integration tests that cover video and photos paths, evidence generation, assisted counting API, and LLM provider strategy wiring, ensuring no regressions and deterministic, contract-stable behavior.

## Scope

**In scope**

- E2E/integration tests: video job and photos job (create → run pipeline with FakeProvider → assert report, evidence_index, artifacts).
- Verification of evidence LOCALIZED vs UNLOCALIZED when using different fixture payloads.
- Assisted counting flow: list entities, get evidence, POST review, GET audit, GET report?resolved=true (for a job that has report + evidence).
- Assertion that pipeline uses provider from factory (FakeProvider in tests); no network calls.
- Fixtures: e.g. `tests/fixtures/v2_1/global_analysis_ok.json`, `global_analysis_unlocalized.json`, and small synthetic photos.

**Out of scope**

- Real Gemini/OpenAI calls in CI.
- Performance benchmarks.

## Architectural Changes

- Tests use temp directories for output; override config (output_dir, LLM_PROVIDER=fake); TestClient for API tests; optional dependency injection for provider in pipeline if needed for clarity.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Create | `tests/fixtures/v2_1/global_analysis_ok.json` (and optionally unlocalized variant). |
| Create | `tests/fixtures/photos/` — 2–3 small synthetic images. |
| Create/Modify | `tests/test_e2e_v2_2.py` (or split) — video E2E, photos E2E, evidence localization, API review flow, provider wiring. |

## Key Implementation Tasks

1. Add fixtures: valid v2.1 global analysis JSON; variant without bboxes for UNLOCALIZED; minimal photo files (e.g. numpy-generated and saved).
2. E2E video: create job (video), run pipeline with FakeProvider returning fixture; assert hybrid_report.json, evidence_index.json, evidence/; assert entity list and counts.
3. E2E photos: create job (photos), run pipeline with FakeProvider; assert input_photos and manifest; assert report and evidence.
4. Evidence: run with bbox vs no-bbox fixture; assert evidence_localization and presence/absence of label crops.
5. API: for a succeeded job with report and evidence, call GET entities, GET evidence, POST review, GET audit, GET report?resolved=true; assert status and body shape.
6. Provider: config LLM_PROVIDER=fake; run pipeline; assert no network; assert request metadata (input_type, frame count).

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Flaky tests | Use temp dirs; deterministic fixtures; no real I/O to shared state. |
| Over-mocking | Prefer one full pipeline run with FakeProvider over many unit mocks. |

## Acceptance Criteria (Definition of Done)

- At least one E2E for video and one for photos.
- Evidence pack verified in both flows; LOCALIZED/UNLOCALIZED covered.
- Assisted counting API flow covered (entities, evidence, review, audit, resolved report).
- Pipeline verified to use provider from factory (FakeProvider); CI green and offline.

## Testing Strategy

- Integration: full pipeline run in temp dir with FakeProvider; assert artifacts and report structure.
- API: TestClient with overridden output_dir and job state; assert status codes and response shapes.
- Determinism: same inputs and config → same report entity order and IDs.

---

# Stage 2.2.F — Hard Cleanup

## Objective

Remove legacy mode and unused code, reduce branching and duplication, and leave a single supported path (hybrid v2.1/v2.2 with video or photos and provider strategy).

## Scope

**In scope**

- Remove legacy mode: reject `mode=legacy` at API (422 with message); remove legacy pipeline code, config, and tests.
- Delete unused modules and dead code; consolidate path/validation/hashing utilities where duplicated.
- Simplify pipeline: one main hybrid flow; FrameSource and LLMProvider as single decision points; remove legacy branches and obsolete fallbacks.

**Out of scope**

- New features or schema changes.
- Large architectural rewrites beyond removal.

## Architectural Changes

- Single supported mode: hybrid (video or photos); no legacy branch. Pipeline entry no longer branches on legacy; job creation rejects legacy. Evidence, report, review unchanged.

## Modules / Files to Create or Modify

| Action | Path |
|--------|------|
| Modify | `src/api/routes/jobs.py` — reject `mode=legacy` (422). |
| Modify | `src/pipeline/hybrid_inventory_pipeline.py` — remove legacy branch and LegacyVisualPipeline usage. |
| Delete | `src/pipeline/legacy_visual_pipeline.py` (and any legacy-only modules). |
| Modify/Delete | Legacy-related tests and config flags. |
| Modify | Consolidate utilities (e.g. validation, paths, hashing) to single modules; remove duplicates. |

## Key Implementation Tasks

1. API: if `mode == "legacy"` or equivalent, return 422 with message that legacy was removed in v2.2.
2. Pipeline: remove `if mode == "legacy"` and call to legacy pipeline; keep only hybrid path (video or photos via FrameSource, LLM via Provider).
3. Delete legacy pipeline module(s) and any code only used by legacy.
4. Remove legacy config options and update docs/README.
5. Consolidate: e.g. job_id/entity_uid validation in one place; path/slug helpers in one place; dedupe/hash if duplicated.
6. Grep for "legacy" and remove or document remaining references (e.g. changelog only).

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking callers that send mode=legacy | Clear 422 message and release notes; clients must switch to hybrid. |
| Deleting code still referenced | Grep all references; run tests after each deletion. |

## Acceptance Criteria (Definition of Done)

- Legacy mode not usable (API rejects with 422); no runtime legacy code.
- Legacy modules and their tests removed; no productive references to "legacy" in code.
- Pipeline has single hybrid flow; fewer branches and duplicated helpers.
- All E2E and unit tests green; docs/README updated.

## Testing Strategy

- test_create_job_rejects_legacy_mode: POST with mode=legacy → 422.
- Existing E2E and unit tests still pass; optional sanity test that no legacy module is imported.

---

# Migration Plan

1. **Implement in order:** A → B → C → D → E → F. Each stage leaves the system in a shippable state.
2. **Feature flags:** Optional: gate photos acceptance (e.g. env ENABLE_PHOTOS_INPUT) until 2.2.E is validated; video path always on.
3. **Database:** If job record is stored in DB, add columns or JSON fields for `input_type`, `input_manifest_path`, `photos_dir` in the same release as 2.2.A; backfill not required for existing jobs.
4. **Rollback:** Disable photos (reject input_type=photos) without rolling back code; video and existing jobs continue to work.

---

# Release Validation Checklist

- [ ] **Video:** Create job (video) → run → hybrid_report.json, evidence_index.json, evidence/ present; entities and review API work.
- [ ] **Photos:** Create job (photos, 2–3 images) → run → input_photos/normalized/, input_manifest.json, report, evidence; entities and review API work.
- [ ] **Limits:** Photos count or total size over limit → 422/413.
- [ ] **Filenames:** Unsafe filename in photos → sanitized; no path traversal.
- [ ] **Provider:** LLM_PROVIDER=gemini → same as v2.1; LLM_PROVIDER=fake → tests pass without network.
- [ ] **Legacy:** mode=legacy → 422; no legacy code in tree.
- [ ] **CI:** All tests pass; lint/type clean.
- [ ] **Docs:** README and API docs describe video and photos input and any new config.
