# Epic 3.1.A — Backend Implementation Plan

**Scope:** Backend-only. Image identity, registration, and prompt enrichment. No traceability parsing, no frontend.

**Source of truth:** `docs/V3/3.1/3.1 - Backlog.md` (Épica 1 + Épica 2 partial), `docs/V3/3.1/3.1 Documento tecnico.md`.

---

## Phase 1 — Analysis summary

### Where uploaded images enter the backend

- **Entry:** `POST /api/v1/inventory/jobs` with `input_type=photos` and multipart `photos` files.
- **Handler:** `api/routes/jobs.py` → `_create_job_photos_form()` → `persist_photos_from_uploads(job_dir, uploads, max_total_bytes)` in `api/photos_handler.py`.
- **Storage:** Files written to `job_dir/run/input_photos/` with `photo_stored_filename()`; manifest to `job_dir/run/input_manifest.json` (relative paths stored in job: `input_manifest_path`, `photos_dir`).
- **Job record:** `job_store.create_job(..., input_type="photos", input_manifest_path=..., photos_dir=...)`; `JobRecord` / `JobInput` in `jobs/models.py`; optional DB via `database/repository.py` `JobsRepository`.

### Where analysis request/prompt is built

- **Pipeline:** `HybridInventoryPipeline` → `InputPreparationStage` → `FrameAcquisitionStage` (uses `PhotosFrameSource.get_frames()` which reads manifest) → `AnalysisStage` → `GeminiAnalysisProvider.analyze()`.
- **Prompt:** `llm/prompts.py` `get_hybrid_prompt(profile_name)` returns static text. `GeminiAnalysisProvider` builds `LLMRequest(job_id, frames, frame_refs, prompt, ...)`; `GeminiProvider.analyze_global(request)` currently **ignores** `request.prompt` and uses `get_hybrid_prompt()` again when constructing `GeminiGlobalAnalyzer`. So enrichment must be done in the adapter and the provider must use `request.prompt` when provided.

### Existing asset representation

- No dedicated `job_images` entity. Manifest is the only structured source: `photos[]` with `index`, `original_filename`, `stored_filename`, `bytes` (and after normalization: `stored_normalized_filename`, etc.). No `image_id` today.

### Integration points for Epic A

1. **photos_handler:** When building `manifest_photos`, add `image_id` per entry (generated here so it is stable and stored once).
2. **Manifest:** Becomes the single source of truth for image identity (no new DB table for Epic A).
3. **PhotosFrameSource:** Use `image_id` from manifest as `frame_ref` when present (backward compat: fallback to `photo_{index:04d}`).
4. **GeminiAnalysisProvider:** For photos jobs, load manifest from `context.run_dir.parent`, build list of `{image_id, original_filename, upload_order}`; call new `enrich_prompt_with_image_ids(base_prompt, images)` and pass enriched prompt in `LLMRequest`.
5. **llm/prompts.py:** Add `enrich_prompt_with_image_ids(prompt, images)` that appends image list + traceability instruction (prepare for future `source_image_id`; no response parsing in Epic A).
6. **GeminiProvider:** Use `request.prompt` when non-empty so the adapter’s enriched prompt is actually sent.

---

## Phase 2 — Backend image identity

- **Convention:** `image_id` = `img_001`, `img_002`, … (1-based, zero-padded to 3 digits). Unique within job.
- **Storage:** Add `image_id` to each entry in `input_manifest.json` `photos[]`. Optional: add a small domain type `JobImage` (dataclass or TypedDict) for in-memory use; manifest remains the persisted form.
- **Model:** Add `JobImage` (or equivalent) with: `image_id`, `job_id`, `original_filename`, `upload_order`, `storage_path` (derived as `photos_dir + "/" + stored_filename`). Used when reading manifest for prompt enrichment; no separate persistence beyond manifest for Epic A.

---

## Phase 3 — Register image metadata in flow

- **Registration:** Done at write time in `persist_photos_from_uploads`: each photo gets `image_id` and manifest is written with it. No extra persistence step.
- **PhotosFrameSource:** When iterating manifest, set `frame_refs[i] = entry.get("image_id") or f"photo_{idx:04d}"` so downstream stages (and provider) see image IDs.
- **Backward compatibility:** Manifests without `image_id` (e.g. existing jobs) continue to work via fallback ref.

---

## Phase 4 — Enrich provider request / prompt

- **prompts.py:** Add `enrich_prompt_with_image_ids(prompt: str, images: List[Dict]) -> str`. Append:
  - A clear list: each image with `image_id`, optional `original_filename`, `upload_order`.
  - Instruction: “For every counted result, return the exact `source_image_id` of the image used as evidence. Do not invent IDs. Only use image IDs provided in the input.” (Prepare for future; no parsing in Epic A.)
- **GeminiAnalysisProvider:** If `job_input.input_type == "photos"` and manifest path is set, load manifest, build `images` list from `photos[]` (image_id, original_filename, index), enrich prompt, pass to `LLMRequest`.
- **GeminiProvider:** Use `request.prompt` when present and non-empty; otherwise fall back to `get_hybrid_prompt(...)`. This ensures the adapter’s enriched prompt is used.

---

## Phase 5 — Tests

- **Unit:** `image_id` generation and manifest shape in `photos_handler`; `enrich_prompt_with_image_ids` adds image list and instruction; `PhotosFrameSource` uses `image_id` when present and fallback when absent.
- **Integration / pipeline:** Job created with photos → manifest has `image_id`; pipeline run (or mocked analysis) receives enriched prompt containing image IDs. No tests for parsing `source_image_id` or traceability_status (Epic B).

---

## Files to create

- `src/jobs/image_identity.py` — `image_id` generation helper and optional `JobImage` type / manifest-to-list loader for analysis layer.

## Files to modify

- `src/api/photos_handler.py` — Add `image_id` to each manifest photo entry.
- `src/frames/sources/photos_source.py` — Use `image_id` as `frame_ref` when present.
- `src/llm/prompts.py` — Add `enrich_prompt_with_image_ids`.
- `src/pipeline/adapters/gemini_analysis_provider.py` — Load manifest for photos jobs, build images list, enrich prompt, pass in request.
- `src/llm/providers/gemini_provider.py` — Use `request.prompt` when non-empty.

---

## Out of scope (left for Epic 3.1.B)

- Parsing `source_image_id` from provider responses.
- Validation of returned image references.
- `traceability_status` / `traceability_warning`.
- Result normalization or persistence of result-to-image mappings.
- Response DTO enrichment with traceability fields.
- Frontend, exports, metrics, multi-evidence implementation.
