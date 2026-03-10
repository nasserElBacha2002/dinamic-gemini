# Feature Plan — Inventory Engine v2.0 Implementation

## Summary

Implement V.2.0 per `docs/V.2.0.md`: controller layer (legacy + hybrid coexistence), single global Gemini call per video, minimal prompt + validation, Pallet entities and report, optimized frame selection, confidence-gated fallback, job-based API, and DB persistence. Delivered in 8 ordered stages with user stories, DB plan, API plan, risks, and global DoD.

## Scope & Non-goals

Execute **Version 2.0** as specified in `docs/V.2.0.md`: core refactor (legacy + hybrid coexistence with `--mode`), single global Gemini call per video, minimal structured prompt, optimized frame selection, confidence-gated visual fallback (CLI/API configurable), job-based API, DB persistence (jobs, pallet_results, job_events), and basic robustness. No v2.1 scope.

## Scope & Non-goals

**In scope (v2.0 only):**
- Etapa 1: HybridInventoryPipeline + LegacyVisualPipeline, `--mode legacy|hybrid` (default legacy).
- Etapa 2: Single Gemini call per video, global analysis.
- Etapa 3: Prompt global minimalista + JSON contract + post-parse validation.
- Etapa 4: Parse/validate → Pallet entities, processing_mode, report generation.
- Etapa 5: Frame selection optimization (15–25 frames, stability + redundancy).
- Etapa 6: `--confidence-threshold`, fallback visual when confidence < threshold.
- Etapa 7: API (POST job, GET status, GET result, GET artifacts, GET /health).
- Etapa 8: DB persistence (jobs, pallet_results, job_events).

**Out of scope:**
- v2.1: multi-worker, advanced observability, auth/roles, cost governance, rate limiting.
- Any feature not explicitly in V.2.0.md.

## Pipeline Placement

| Stage   | Placement in pipeline |
|--------|------------------------|
| 1      | Entry point / controller (above detection → tracking → … → reporting). |
| 2–4    | New path: Video → frame extraction (v2) → 1 Gemini call → parse → Pallet entities → report. |
| 5      | Input to hybrid path: frame extraction (optimized). |
| 6      | Post–global call: per-pallet decision → optional fallback call. |
| 7–8    | Wraps execution: API/CLI → job lifecycle → engine run → persist. |

Legacy path (detection → tracking → view selection → Gemini per track → consolidate) remains unchanged and is invoked only when `mode=legacy`.

## Config / Flags

- **CLI:** `--mode legacy|hybrid` (default `legacy`); `--confidence-threshold` float in [0,1] (default 0.70, hybrid only).
- **Config (env/code):** `confidence_threshold`; hybrid frame selection: base_interval_sec, similarity_threshold, hybrid_frames_min/max (e.g. 15–25).
- **API:** Same options per request: mode, confidence_threshold (body or form).

## Acceptance Criteria (Global)

- Legacy mode behaviour and output unchanged; all existing tests pass.
- Hybrid: exactly one global Gemini call; additional calls only when fallback is triggered. **gemini_calls = 1 + fallback_calls_count** is persisted in jobs table and verifiable.
- Parse/validate; report with pallet_id, internal_code, quantity, source, confidence, fallback_used.
- Fallback runs when confidence < threshold (or required fields null); report reflects fallback_used.
- API: POST job → 202; GET status/result/artifacts; GET /health.
- DB: jobs, pallet_results, job_events persisted; status/result read from DB; engine_version and prompt_version stored at job creation from config.

## Risks & De-risk Plan

- **Invalid/hallucinated JSON:** Strict prompt + parse_and_validate + one retry; fail job with error_code; log raw response.
- **Missing pallets in frames:** 15–25 frames with uniform + redundancy filter; accept global inference limit; tests with known videos.
- **Fallback over/under-trigger:** Configurable threshold; explicit should_fallback rules; tests for low-confidence and null fields.
- **Concurrency/partial writes:** Unique job id; one transaction per state change; write artifacts then update DB paths.

---

# Part 1 — High-Level Implementation Phases (Stages)

## Stage 1 — Core Rearchitecture (Convivencia legacy + hybrid)

**Goal:** Introduce `HybridInventoryPipeline` and encapsulate current behaviour in `LegacyVisualPipeline`; add `--mode legacy|hybrid` (default `legacy`). No new business logic.

**Scope included:** New controller class, legacy wrapper, CLI `--mode`, entry-point routing.  
**Scope excluded:** Hybrid logic (Stage 2+), API, DB.  
**Dependencies:** None (first stage).

---

## Stage 2 — Single Global Gemini Call (Analysis Global por Video)

**Goal:** Implement hybrid path: extract representative frames → one Gemini call with global prompt → structured response (total_pallets_detected + pallets array).

**Scope included:** Global frame extraction (simple uniform first), global prompt, one `analyze_global` (or equivalent) call, raw JSON response handling.  
**Scope excluded:** Validation/strict parsing (Stage 3), Pallet entities and report (Stage 4), frame optimization (Stage 5), fallback (Stage 6).  
**Dependencies:** Stage 1 (run_hybrid delegates to new module).

---

## Stage 3 — Minimal Prompt & Validation

**Goal:** Finalize global prompt (minimal, deterministic), define strict JSON schema, implement parse + validation (total_pallets_detected == len(pallets), no duplicate pallet_id, has_label/quantity/estimated_visible_boxes rules, confidence in [0,1]). One retry on parse/validation failure.

**Scope included:** Prompt text, response schema, validation module, retry on invalid.  
**Scope excluded:** Pallet domain model and report format (Stage 4).  
**Dependencies:** Stage 2 (response shape exists).

---

## Stage 4 — Operational Integration (Parse → Pallets → Report)

**Goal:** Convert validated JSON into internal Pallet entities, set processing_mode (label | visual_fallback), final_quantity; handle edge cases (0 pallets, low confidence flag); generate v2.0 report (pallet_id, internal_code, quantity, source, confidence, fallback_used).

**Scope included:** Pallet model (v2), assign_processing_modes, report generator, run_hybrid orchestration.  
**Scope excluded:** Real fallback execution (Stage 6), API/DB.  
**Dependencies:** Stage 3.

---

## Stage 5 — Optimized Frame Selection

**Goal:** Replace simple uniform sampling with three-step selection: base uniform sampling (e.g. 1 frame every 4–6 s → ~15–30 frames), redundancy filter (e.g. pHash/histogram vs last accepted), stability filter (avoid transition/motion-blur frames). Target 15–25 final frames.

**Scope included:** New or extended module for representative frame extraction, config (base_interval, similarity threshold, stability criteria).  
**Scope excluded:** Changing Gemini prompt or response format.  
**Dependencies:** Stage 2 (hybrid path uses frame list).

---

## Stage 6 — Confidence-Gated Visual Fallback

**Goal:** Add `--confidence-threshold` (default 0.70). For each pallet, if confidence < threshold or required fields null → run visual fallback (3–5 frames, count prompt, median consolidation). Preserve internal_code when only quantity is low-confidence. Report includes source and fallback_used.

**Scope included:** CLI/config threshold, should_fallback logic, fallback prompt, median consolidation, report fields.  
**Scope excluded:** API/DB (Stage 7–8).  
**Dependencies:** Stage 4 (Pallet + report).

---

## Stage 7 — API Layer (Job-Based)

**Goal:** Expose engine as service: POST create job (video upload, mode, confidence_threshold), GET job status (with progress), GET result, GET artifacts (links/paths), GET /health. Async job execution (in-process worker or background thread acceptable for v2.0).

**Scope included:** API server (e.g. FastAPI), routes, request/response schemas, job store in memory or DB (Stage 8 can replace in-memory with DB).  
**Scope excluded:** DB as source of truth (Stage 8), multi-worker.  
**Dependencies:** Stage 1 (mode), Stage 6 (confidence_threshold). Optional: Stage 8 can follow or run in parallel with 7.

---

## Stage 8 — DB Persistence

**Goal:** DB as source of truth for jobs: tables jobs, pallet_results, job_events; migrations; write on create/start/complete/fail; read for status and result endpoints; artifacts on filesystem, paths in DB.

**Scope included:** Schema, migrations, job_store implementation using DB, transaction boundaries, status transitions; **engine_version and prompt_version** set from config at job creation and persisted in jobs table.  
**Scope excluded:** Multi-tenant, users/roles, S3/GCS (paths in DB ready for future).  
**Dependencies:** Stage 7 (API contract); can implement API with in-memory store first then swap to DB.

---

# Part 2 — Module-Level Task Breakdown

## Stage 1 — Core Rearchitecture

- **Create:** `src/pipeline/legacy_visual_pipeline.py`
  - Class `LegacyVisualPipeline` with method `run(video_path, video_id, output_dir, run_id, **kwargs)` that contains **all** legacy execution logic. Move into it: (1) **Track-based path:** load metadata, extract frames, detect, track, ROI, (optional Re-ID), view selection, Gemini per track, build FinalResult — by calling `run_pipeline` from `src/pipeline/orchestrator.py`. (2) **Frame-based path:** extract frames, select frames, prepare for API, analyze_frames, consolidate, build FinalResult — all logic currently in `src/app.py` must be moved here (no reuse of logic from app; app must not contain it). Both code paths live entirely inside `LegacyVisualPipeline`.
- **Create:** `src/pipeline/hybrid_inventory_pipeline.py`
  - Class `HybridInventoryPipeline` with `process_video(path, mode="legacy", **kwargs)`. If `mode == "legacy"` call `LegacyVisualPipeline().run(...)`. If `mode == "hybrid"` call `self._run_hybrid(path, **kwargs)` which for now delegates to legacy (stub).
- **Refactor:** `src/app.py`
  - **Thin entrypoint only:** Parse args (including `--mode` with choices `["legacy", "hybrid"]`, default `legacy`); load settings; validate video; compute video_id, output_dir, run_id; instantiate `HybridInventoryPipeline`; call `process_video(video_path, mode=args.mode, ...)` passing through CLI args. **No business logic remains in app.py:** no frame extraction, no run_pipeline calls, no consolidate, no Gemini usage. All execution is delegated to the pipeline classes.
- **Contracts:** No new public data contracts; existing `FinalResult`, `PalletEstimate`, etc. remain.
- **Tests:** `tests/test_hybrid_pipeline.py`: (1) `--mode legacy` produces same behaviour as current app (track path and frame path covered by existing tests or minimal integration test). (2) `--mode hybrid` runs without error and returns (stub can return legacy result).

---

## Stage 2 — Single Global Gemini Call

- **Refactor:** `src/video/frames.py`
  - **Reuse and extend existing module;** do not create a parallel frame extractor. Add a hybrid strategy: e.g. `extract_frames(video_path, target_fps=..., strategy="uniform")` or a dedicated `extract_representative_frames(video_path, base_interval_sec=4)` that uses the same video opening and frame iteration as existing `extract_frames`, producing ~15–30 FrameRefs for hybrid. All frame extraction for hybrid flows through this module.
- **Create:** `src/pipeline/hybrid_flow.py` (or `src/hybrid/global_analysis.py`)
  - Call `extract_frames` (or the new hybrid entry point) from `src/video/frames.py` to obtain FrameRef list; no duplicate extraction logic. `run_global_analysis(video_path, frames, image_paths, client, prompt_profile)` → raw string or dict from Gemini (one request with all images).
- **Refactor:** `src/llm/gemini_client.py`
  - Add method e.g. `analyze_global(frames, image_paths, prompt_profile="global_v2")` that builds one multi-part request, sends to Gemini, returns raw response text (or parsed JSON if desired early).
- **Refactor:** `src/llm/prompts.py`
  - Add profile `global_v2` (or similar) with the Etapa 2/3 global prompt (placeholder or final minimal text from V.2.0.md).
- **Refactor:** `src/pipeline/hybrid_inventory_pipeline.py`
  - `_run_hybrid(path, **kwargs)`: call `extract_representative_frames`, prepare images (reuse or mirror `prepare_frames_for_api`), call `client.analyze_global(...)`, return raw response for Stage 3 to parse.
- **Contracts:** Response shape as in V.2.0.md: `{ "total_pallets_detected": int, "pallets": [ { "pallet_id", "has_label", "internal_code", "quantity", "estimated_visible_boxes", "confidence" } ] }`. No validation yet.
- **Tests:** Unit test for `analyze_global` (mock client); integration-style test that hybrid path returns a structure with `total_pallets_detected` and `pallets` (mock Gemini).

---

## Stage 3 — Minimal Prompt & Validation

- **Refactor:** `src/llm/prompts.py`
  - Set final “Single Call Minimal” prompt (V.2.0.md Etapa 3): strict JSON, no markdown, no extra text.
- **Create:** `src/hybrid/validation.py` (or under `src/pipeline/`)
  - `parse_global_response(text: str) -> dict`: json.loads, strip markdown if needed, return dict.
  - `validate_global_response(data: dict) -> tuple[bool, list[str]]`: check total_pallets_detected == len(pallets), unique pallet_id, has_label true → quantity not null, has_label false → estimated_visible_boxes not null, confidence in [0,1]. Return (ok, list of errors).
  - `parse_and_validate(text, retry_once=True)`: parse; if validation fails and retry_once, optional repair (e.g. re-request not required in spec; “1 retry” can mean one re-parse/repair attempt), then validate again; return validated data or raise/return error.
- **Contracts:** Same JSON schema; validation rules documented in code and aligned to V.2.0.md.
- **Tests:** Tests for parse (valid JSON, invalid JSON, wrapped in markdown); validation (all rules); parse_and_validate with invalid then valid.

---

## Stage 4 — Operational Integration

- **Create:** `src/hybrid/pallet_v2.py` (or extend `src/models/schemas.py`)
  - Class `Pallet` (or `PalletV2`): id, has_label, internal_code, quantity, estimated_visible_boxes, confidence, processing_mode, final_quantity (and optional raw fields for audit).
- **Create:** `src/hybrid/report.py`
  - `build_pallet_objects(validated_data: dict) -> list[Pallet]`.
  - `assign_processing_modes(pallets: list[Pallet])`: label vs visual_fallback per V.2.0.md (has_label + internal_code + quantity → label; else visual_fallback).
  - `generate_report(pallets: list[Pallet]) -> list[dict]`: list of { pallet_id, internal_code, quantity, source, confidence, fallback_used }.
  - Edge cases: 0 pallets → status no_pallets_detected; confidence < 0.4 → flag low_confidence_review (do not block).
- **Refactor:** `src/pipeline/hybrid_inventory_pipeline.py`
  - `_run_hybrid`: after global call → parse_and_validate → build_pallet_objects → assign_processing_modes → generate_report; return report + metadata (frames_count, etc.). No fallback execution yet.
- **Contracts:** Report format as in V.2.0.md Etapa 4 (source: "label" | "visual_fallback").
- **Tests:** build_pallet_objects, assign_processing_modes, generate_report (unit); _run_hybrid returns report with expected keys.

---

## Stage 5 — Optimized Frame Selection

- **Refactor:** `src/video/frames.py`
  - **Avoid duplicating frame extraction.** Extend the existing module with hybrid strategy: e.g. add `extract_representative_frames(video_path, base_interval_sec=4, similarity_threshold=0.95, target_min=15, target_max=25) -> list[FrameRef]` that (1) uses existing uniform sampling (same video read path as `extract_frames`), (2) applies redundancy filter (e.g. pHash or histogram; reuse `src/preprocess/similarity.py` if available), (3) optionally applies stability check (motion/blur). All hybrid frame selection lives in this module; do not create a separate `src/hybrid/frame_selection.py` with parallel implementation.
- **Refactor:** `src/config.py`
  - Add `hybrid_base_interval_sec`, `hybrid_similarity_threshold`, `hybrid_frames_min`, `hybrid_frames_max` (or single namespace).
- **Refactor:** `src/pipeline/hybrid_flow.py` (or equivalent)
  - Call `extract_representative_frames` from `src/video/frames.py` for the hybrid path.
- **Tests:** Unit tests: redundancy filter drops near-duplicates; stability filter (if used); final count in [15, 25] for a 2-min video.

---

## Stage 6 — Confidence-Gated Visual Fallback

- **Refactor:** `src/config.py`
  - Add `confidence_threshold: float = 0.70` (and from env).
- **Refactor:** `src/app.py`
  - Add `--confidence-threshold` (float 0–1, default 0.70); pass to `process_video(..., confidence_threshold=...)`.
- **Create:** `src/hybrid/fallback.py`
  - `should_fallback(pallet, threshold) -> bool`: confidence < threshold, or has_label and (quantity is None or internal_code is None), or not has_label and estimated_visible_boxes is None.
  - `run_fallback_for_pallet(pallet, video_path, frame_refs, client) -> { estimated_count, confidence }`: select 3–5 frames, send count prompt, return median count and average confidence.
- **Refactor:** `src/llm/prompts.py`
  - Add fallback prompt (count boxes, strict JSON: estimated_count, confidence).
- **Refactor:** `src/llm/gemini_client.py`
  - Add `estimate_pallet_boxes(frames, image_paths)` for fallback call.
- **Refactor:** `src/hybrid/report.py` / `assign_processing_modes`
  - After global result: for each pallet call should_fallback; if True run fallback, set final_quantity to median, keep internal_code if already set; set source and fallback_used in report.
- **Gemini call accounting:** Hybrid mode must always perform exactly **one** global Gemini call. Additional calls are **only** fallback-triggered (one call per pallet that triggers fallback). Define and persist: `gemini_calls = 1 + fallback_calls_count`. Worker/pipeline must set this on job completion and store it in the `jobs` table (Stage 8).
- **Contracts:** Report includes fallback_used; final_quantity from label or fallback.
- **Tests:** should_fallback (threshold and null cases); run_fallback_for_pallet (mock); integration: hybrid with low-confidence pallet triggers fallback and report shows fallback_used; test that gemini_calls = 1 when no fallback and 1 + N when N fallbacks run.

---

## Stage 7 — API Layer

- **Create:** `src/api/server.py`
  - FastAPI app; CORS if needed; register routes.
- **Create:** `src/api/routes/jobs.py`
  - POST `/api/v1/inventory/jobs`: multipart video, mode, confidence_threshold, metadata (optional). Create job (in-memory or DB), return 202 { job_id, status: "queued", mode, confidence_threshold }.
  - GET `/api/v1/inventory/jobs/{job_id}`: return status, progress (stage, percent), created_at.
  - GET `/api/v1/inventory/jobs/{job_id}/result`: when succeeded, return report (video_id, mode, confidence_threshold, pallets).
  - GET `/api/v1/inventory/jobs/{job_id}/artifacts`: list of artifact paths/links (report.json, report.csv, selected_frames/, etc.).
- **Create:** `src/api/routes/health.py`
  - GET `/health` → { "ok": true }.
- **Create:** `src/api/schemas/requests.py` and `responses.py`
  - Request: job creation (video file, mode, confidence_threshold). Response: job created, job status, job result, artifacts list.
- **Create:** `src/jobs/queue.py` and `src/jobs/worker.py` (or single module)
  - Job store (dict or DB interface); worker runs HybridInventoryPipeline.process_video in background (thread or async), updates status and progress, writes artifacts to output dir, stores paths in job.
- **Refactor:** `src/pipeline/hybrid_inventory_pipeline.py`
  - Accept confidence_threshold and mode from API; same as CLI.
- **Contracts:** API contract as in V.2.0.md Etapa 7 (statuses: queued, running, succeeded, failed).
- **Tests:** API tests: create job 202; get status; get result when succeeded; get artifacts; health. Worker test: run job and assert status transitions.

---

## Stage 8 — DB Persistence

- **Define version constants (config):** In `src/config.py` (or a dedicated constants module) define explicitly: `ENGINE_VERSION = "2.0"` and `PROMPT_VERSION = "global_min_v1"`. These values must be stored in the `jobs` table on job creation (fields `engine_version`, `prompt_version`).
- **Create:** DB schema (e.g. SQLAlchemy models or raw SQL migrations)
  - Table `jobs`: id (PK), created_at, updated_at, status, mode, confidence_threshold, video_filename, video_path, frames_count_sent, **gemini_calls** (int: 1 for global call + fallback_calls_count; must be persisted on job completion), progress_stage, progress_percent, error_code, error_message, artifacts_dir, report_json_path, report_csv_path, **engine_version**, **prompt_version** (set from config constants at job creation), metadata (JSON).
  - Table `pallet_results`: id (PK), job_id (FK), pallet_id, internal_code, quantity, source, confidence, fallback_used, raw_estimated_visible_boxes, created_at.
  - Table `job_events`: id (PK), job_id (FK), timestamp, event_type, payload (JSON).
- **Create:** Migrations (e.g. Alembic or timestamped SQL files); run in order.
- **Create:** `src/jobs/job_store.py` (or extend existing)
  - Implement with DB: create job (with engine_version, prompt_version from config), update status/progress, set output paths and gemini_calls, insert pallet_results, append job_events. Transaction boundaries: one transaction per state change (or per job completion with pallet_results).
- **Refactor:** `src/api/routes/jobs.py` and worker
  - Use DB job_store instead of in-memory; GET status/result read from DB; artifacts_dir and report paths from jobs table.
- **Indexes:** job_id on pallet_results and job_events; status, created_at on jobs for listing/filtering.
- **Consistency:** status transitions: queued → running → succeeded | failed; succeeded ⇒ report_json_path set; failed ⇒ error_code set.
- **Acceptance criteria:** engine_version and prompt_version are set at job creation from config (ENGINE_VERSION, PROMPT_VERSION) and persisted in jobs table; gemini_calls is set on completion and equals 1 + fallback_calls_count for hybrid jobs.
- **Tests:** DB tests: create job, update to running, complete with pallet_results and events; read result; constraint checks; verify engine_version and prompt_version stored on create; verify gemini_calls persisted.

---

# Part 3 — User Stories per Stage

## Stage 1 — Core Rearchitecture

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S1-1 | Mode selection via CLI | Operations Manager | to run the system with `--mode legacy` or `--mode hybrid` | we can keep using the current behaviour or switch to the new hybrid path without code changes | CLI accepts `--mode legacy` and `--mode hybrid`; default is legacy. Both modes execute without error. | Implemented and tested; legacy behaviour unchanged. | P0 | V.2.0 § Etapa 1 |
| S1-2 | Legacy behaviour preserved | Developer / Maintainer | the existing track and frame-based pipelines to be encapsulated and unchanged | we do not regress production or tests | With `--mode legacy`, output and behaviour match current app (track and frame-based paths). | All existing pipeline tests pass; no change in FinalResult shape for legacy. | P0 | Same |
| S1-3 | Hybrid stub | System Admin | `--mode hybrid` to run without error and return a result | we can deploy the new entry point before hybrid logic is ready | With `--mode hybrid`, pipeline runs and returns (e.g. legacy result or placeholder). | Hybrid path executes and returns; no crash. | P1 | run_hybrid delegates to legacy |

---

## Stage 2 — Single Global Gemini Call

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S2-1 | One call per video | Operations Manager | the hybrid path to send one Gemini request per video with selected frames | we reduce cost and simplify the flow | Hybrid run sends exactly one Gemini request containing multiple frames; response has total_pallets_detected and pallets array. | Verified in test or log; response shape documented. | P0 | V.2.0 § Etapa 2 |
| S2-2 | Representative frames | Developer / Maintainer | the system to extract 15–30 representative frames (simple uniform first) | each pallet is likely visible at least once | Frames are extracted with configurable interval (e.g. 4–6 s); count in 15–30 for typical 2 min video. | Config + code; test with sample video. | P0 | Same |
| S2-3 | Global prompt and response | Integration Client | the global analysis to return structured pallet list | our systems can consume a single response | Response is JSON with total_pallets_detected and pallets (pallet_id, has_label, internal_code, quantity, estimated_visible_boxes, confidence). | Schema documented; client method returns this structure (raw or parsed). | P0 | Etapa 2–3 |
| S2-4 | Single global call verification | System Admin | to verify that hybrid mode performs only one global Gemini call | we ensure predictable API cost | Hybrid run performs exactly one global analysis call; any additional Gemini calls are only fallback-triggered (Stage 6). gemini_calls = 1 + fallback_calls_count is persisted (Stage 8) and verifiable. | Test or metric confirms single global call; acceptance criteria for gemini_calls in Stage 6/8. | P0 | Etapa 2 |

---

## Stage 3 — Minimal Prompt & Validation

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S3-1 | Strict JSON response | Developer / Maintainer | the global prompt to require only valid JSON with no markdown or extra text | parsing is reliable and we avoid hallucination | Prompt text matches V.2.0 minimal prompt; response is parseable JSON. | Prompt in code; unit test with mock response. | P0 | V.2.0 § Etapa 3 |
| S3-2 | Validation rules | Operations Manager | invalid responses to be detected and optionally retried once | we do not persist bad data | total_pallets_detected == len(pallets); no duplicate pallet_id; has_label/quantity/estimated_visible_boxes consistency; confidence in [0,1]. One retry on failure. | Validation module with tests for each rule; integration uses it. | P0 | Same |
| S3-3 | Parse robustness | System Admin | the system to handle malformed JSON (strip markdown, one repair attempt) | occasional model mistakes do not fail the job | parse_and_validate strips markdown if needed and retries once; returns validated dict or clear error. | Tests for valid, invalid, wrapped responses. | P1 | Same |

---

## Stage 4 — Operational Integration

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S4-1 | Pallet entities and modes | Developer / Maintainer | each validated pallet to become an internal Pallet with processing_mode (label | visual_fallback) | we can later trigger fallback only when needed | build_pallet_objects and assign_processing_modes implemented; report includes source (label | visual_fallback). | Unit tests; report structure as in spec. | P0 | V.2.0 § Etapa 4 |
| S4-2 | Report generation | Warehouse Operator | a single report listing each pallet with quantity, source, and confidence | I can use the result for inventory | Report has pallet_id, internal_code, quantity, source, confidence, fallback_used. | generate_report tested; _run_hybrid returns this report. | P0 | Same |
| S4-3 | Edge cases | System Admin | 0 pallets and very low confidence to be handled without crashing | we get explicit status and optional review flags | 0 pallets → status no_pallets_detected; confidence < 0.4 → low_confidence_review flag (no block). | Handled in code and tests. | P1 | Same |

---

## Stage 5 — Optimized Frame Selection

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S5-1 | Fewer, better frames | Operations Manager | the hybrid path to use 15–25 curated frames instead of 30+ | we balance quality and token cost | Final frame set in [15, 25] for a ~2 min video; configurable. | extract_representative_frames returns list in range; tests. | P0 | V.2.0 § Etapa 5 |
| S5-2 | Redundancy filter | Developer / Maintainer | near-duplicate frames to be dropped (e.g. same pallet, same pose) | we avoid redundant tokens | Similarity (e.g. pHash) vs last accepted; threshold configurable; redundant frames excluded. | Filter implemented and tested. | P0 | Same |
| S5-3 | Stability filter | Developer / Maintainer | frames in strong transition or motion blur to be deprioritized or skipped | we prefer stable views for labels | Optional stability check; configurable. | Implemented and tested or documented as optional. | P1 | Same |

---

## Stage 6 — Confidence-Gated Fallback

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S6-1 | Configurable threshold | Operations Manager | to set a confidence threshold (e.g. 0.70) via CLI so that below it we run visual fallback | we can tune per depot or client | --confidence-threshold 0.70 (default); used in should_fallback. | CLI and config; used in pipeline. | P0 | V.2.0 § Etapa 6 |
| S6-2 | Fallback execution | Warehouse Operator | pallets with low confidence or missing quantity to get an estimated count from extra frames | I get a quantity even when the label is unclear | When should_fallback is True, 3–5 frames sent with count prompt; median count and avg confidence; final_quantity and report updated. | run_fallback_for_pallet and integration test. | P0 | Same |
| S6-3 | Preserve label data | Integration Client | when only quantity is low-confidence, to keep internal_code and only replace quantity with fallback | we do not lose good metadata | If has_label and internal_code present, keep them; replace quantity with fallback result when needed. | Logic in report/fallback module; test. | P0 | Same |

---

## Stage 7 — API Layer

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S7-1 | Create job | Integration Client | to POST a video and options (mode, confidence_threshold) and receive a job_id | I can process videos without using the CLI | POST /api/v1/inventory/jobs returns 202 with job_id, status queued, mode, confidence_threshold. | Route and schema; test. | P0 | V.2.0 § Etapa 7 |
| S7-2 | Job status and result | Integration Client | to GET job status and then the final result when ready | I can poll and then fetch the report | GET /jobs/{id} returns status and progress; GET /jobs/{id}/result returns report when succeeded. | Implemented and tested. | P0 | Same |
| S7-3 | Artifacts and health | System Admin | to list artifacts (report.json, frames, etc.) and check service health | I can debug and monitor | GET /jobs/{id}/artifacts returns list; GET /health returns { "ok": true }. | Implemented and tested. | P1 | Same |

---

## Stage 8 — DB Persistence

| ID   | Title | As a … | I want … | So that … | Acceptance Criteria | DoD | Priority | Notes |
|------|--------|--------|----------|-----------|---------------------|-----|----------|------|
| S8-1 | Jobs and results in DB | Operations Manager | every job and its pallet results to be stored in the database | we have a single source of truth and can audit | jobs and pallet_results tables populated; status and paths updated. | Schema and job_store; tests. | P0 | V.2.0 § Etapa 8 |
| S8-2 | Job events | Developer / Maintainer | key events (e.g. FRAMES_SELECTED, GEMINI_CALL, REPORT_WRITTEN) to be logged in job_events | we can debug and trace execution | job_events inserted at defined stages; queryable by job_id. | Events documented and written; test. | P1 | Same |
| S8-3 | API reads from DB | Integration Client | status and result endpoints to read from the database | behaviour is consistent with CLI and workers | GET status/result use DB; no dependency on in-memory only. | API integration test with DB. | P0 | Same |
| S8-4 | Engine and prompt version stored | Developer / Maintainer | ENGINE_VERSION and PROMPT_VERSION to be defined in config and stored in jobs at creation | we can reproduce and audit which engine/prompt was used | ENGINE_VERSION = "2.0", PROMPT_VERSION = "global_min_v1" in config; both stored in jobs.engine_version and jobs.prompt_version on job creation. | Task in Stage 8; acceptance criteria and test. | P0 | Etapa 8 |

---

# Part 4 — Database Implementation Plan

## Tables and Relationships

- **jobs** (1) ──< **pallet_results** (N): one job has many pallet_results.
- **jobs** (1) ──< **job_events** (N): one job has many events.

## Table Definitions (conceptual)

**jobs**
- `id` (PK, UUID or string).
- `created_at`, `updated_at` (timestamp).
- `status` (enum: queued, running, succeeded, failed, canceled).
- `mode` (legacy | hybrid).
- `confidence_threshold` (float).
- `video_filename`, `video_path` (string).
- `frames_count_sent` (int, nullable).
- **`gemini_calls`** (int, nullable): for hybrid jobs, **must equal 1 (global call) + fallback_calls_count**; persisted on job completion.
- `progress_stage`, `progress_percent` (string, int, nullable).
- `error_code`, `error_message` (string, nullable).
- `artifacts_dir`, `report_json_path`, `report_csv_path` (string, nullable).
- **`engine_version`**, **`prompt_version`** (string, nullable): set from config constants (ENGINE_VERSION = "2.0", PROMPT_VERSION = "global_min_v1") at job creation.
- `metadata` (JSON, nullable).

**pallet_results**
- `id` (PK).
- `job_id` (FK → jobs.id).
- `pallet_id` (string).
- `internal_code`, `quantity` (nullable).
- `source` (label | visual_fallback | legacy).
- `confidence` (float, nullable).
- `fallback_used` (boolean).
- `raw_estimated_visible_boxes` (int, nullable).
- `created_at`.

**job_events**
- `id` (PK).
- `job_id` (FK → jobs.id).
- `timestamp`.
- `event_type` (string).
- `payload` (JSON).

## Migration Order

1. Create `jobs`.
2. Create `pallet_results` (FK to jobs).
3. Create `job_events` (FK to jobs).

## Indexes

- `jobs`: (status), (created_at), (id) primary.
- `pallet_results`: (job_id), (job_id, pallet_id) if unique per job.
- `job_events`: (job_id), (job_id, timestamp).

## Transaction Boundaries

- Create job: one transaction (insert jobs).
- Start job: one transaction (update jobs set status=running, progress).
- Complete job: one transaction (update jobs, insert pallet_results, insert job_events for completion).
- Fail job: one transaction (update jobs with error_*, insert job_events for failure).

## Consistency Constraints

- status in (queued, running, succeeded, failed, canceled).
- succeeded ⇒ report_json_path is not null.
- failed ⇒ error_code is not null.
- pallet_results.job_id must exist in jobs.

---

# Part 5 — API Implementation Plan

## Endpoint List

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/v1/inventory/jobs | Create job (video upload, mode, confidence_threshold). |
| GET | /api/v1/inventory/jobs/{job_id} | Get status and progress. |
| GET | /api/v1/inventory/jobs/{job_id}/result | Get report (when succeeded). |
| GET | /api/v1/inventory/jobs/{job_id}/artifacts | List artifact paths/links. |
| GET | /health | Healthcheck. |

## Request/Response Schemas

- **POST /jobs**: multipart/form-data: video (file), mode (legacy|hybrid), confidence_threshold (float, optional). Optional: metadata (JSON string). Response 202: { job_id, status: "queued", mode, confidence_threshold }.
- **GET /jobs/{id}**: 200: { job_id, status, progress: { stage, percent }, created_at }.
- **GET /jobs/{id}/result**: 200: { job_id, status: "succeeded", report: { video_id, mode, confidence_threshold, pallets: [...] } }; 404 or 409 if not ready/failed.
- **GET /jobs/{id}/artifacts**: 200: { report_json, report_csv, selected_frames_dir, ... } or list of paths.
- **GET /health**: 200: { "ok": true }.

## Error Codes Strategy

- 400: Bad request (invalid mode, missing video, threshold out of range).
- 404: Job not found.
- 409: Job not succeeded (e.g. when requesting result for running/queued/failed).
- 500: Internal error (with optional error_code in body for failed jobs).

## Job Lifecycle State Machine

- queued → running → succeeded | failed.
- Only running can transition to succeeded or failed; optional canceled from queued.

## File Upload Handling

- Accept multipart; save video to temp or configured storage; store path in job; pass path to worker; limit file size (configurable).

## Artifacts Access

- Artifacts on filesystem under output/{job_id}/; DB stores artifacts_dir and report paths. API returns paths or signed links (v2.0 can return paths only).

---

# Part 6 — Risk Assessment

| Risk | Mitigation |
|------|------------|
| Gemini returns invalid JSON or hallucinated structure | Strict prompt; parse_and_validate with one retry; mark job failed with error_code if still invalid; log raw response for debugging. |
| Frame selection misses a pallet | Target 15–25 frames with uniform base + redundancy filter; accept “inference global” limitation per V.2.0; optional stability filter; monitor missed pallets in tests. |
| Fallback over-triggering (too many extra calls) | Threshold configurable; only run when should_fallback true; cap fallback frames (3–5); consider cost alerts in v2.1. |
| Fallback under-triggering (missing low-confidence cases) | Explicit should_fallback rules (confidence, null quantity/internal_code/estimated_visible_boxes); tests with low-confidence payloads. |
| Concurrency / duplicate jobs | Job id unique (UUID); create job in one transaction; worker picks queued jobs (single worker v2.0). |
| Partial writes to DB / artifacts | One transaction per state transition; write artifacts to disk then update job with paths; on failure set status failed and error_* so result endpoint does not return partial data. |

---

# Part 7 — v2.0 Definition of Done (Global)

- **Legacy mode unchanged:** With `--mode legacy`, track and frame-based behaviour and outputs match current app; all existing pipeline and app tests pass.
- **Hybrid mode end-to-end:** With `--mode hybrid`, one global Gemini call is sent; response is parsed and validated; Pallet entities and report are generated; confidence_threshold and fallback (when applicable) are applied; report includes source and fallback_used.
- **Single-call verified:** In hybrid mode, exactly one Gemini call for global analysis (plus N fallback calls only when threshold triggers). **gemini_calls** (1 + fallback_calls_count) is persisted in jobs and verifiable.
- **Confidence-threshold fallback verified:** When confidence < threshold (or required fields null), fallback runs and report reflects fallback_used and correct quantity.
- **API + DB job lifecycle verified:** POST job → 202; GET status shows running then succeeded/failed; GET result returns report when succeeded; GET artifacts returns paths; jobs and pallet_results and job_events persisted and readable.
- **Reports generated and stored:** report.json (and optionally report.csv) written under job output dir and paths stored in DB; report structure matches V.2.0 (pallet_id, internal_code, quantity, source, confidence, fallback_used).
- **No v2.1 scope:** No multi-worker, advanced observability, auth/roles, or cost governance in this release.

---

# Notes / Open Questions

- **Entry point:** V.2.0 mentions `run.py`; repo uses `python -m src.app`. Plan uses existing `src.app` and adds `--mode`; a separate `run.py` can be a thin wrapper calling the same pipeline if desired.
- **Legacy encapsulation:** “Legacy” includes both (1) track pipeline (--track-pipeline) and (2) frame-based pipeline (no --track-pipeline). Both are invoked via LegacyVisualPipeline so one `--mode legacy` preserves current behaviour for both entry styles.
- **Engine/prompt version:** Define in config ENGINE_VERSION = "2.0" and PROMPT_VERSION = "global_min_v1"; store both in jobs table at job creation (Stage 8).
