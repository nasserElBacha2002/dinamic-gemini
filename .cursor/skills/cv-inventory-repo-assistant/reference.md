# CV Inventory — Pipeline and contracts reference

Summary for the CV Inventory Repo Assistant skill. Full detail: repo root `PLAN_IMPLEMENTACION.md`.

## Target repo structure (src/)

| Area | Modules | Role |
|------|---------|------|
| **models** | `schemas.py`, `contracts.py` | Pydantic schemas, MinifiedTrackResult, PalletObservation, PalletTrack |
| **video** | `ingest.py`, `frames.py` | Video load, frame extraction |
| **detection** | `pallet_detector.py`, `clustering.py` | Pallets per frame → List[BBox] |
| **tracking** | `tracker.py`, `track_builder.py` | BBox stream → stable pallet_track_id, List[PalletTrack] |
| **roi** | `cropper.py`, `quality.py` | Crop ROI, blur score |
| **view_selection** | `selector.py`, `diversity.py` | 3–5 views per track |
| **llm** | `prompts.py`, `gemini_client.py` | 1 request per track → MinifiedTrackResult |
| **validation** | `segregation.py`, `determinism.py`, `normalizer.py` | One product per pallet, strict counting |
| **reid** | `signature.py`, `gating.py`, `phash.py`, `clip_embedder.py`, `merge.py` | Track merging (Sprint C) |
| **pipeline** | `orchestrator.py`, `stages.py` | run_pipeline(video_path, config) |
| **io** | `outputs.py`, `logging.py` | final_result.json, errors.json, logs |

Current codebase may have `preprocess/`, `consolidate/` in place of some of the above; align new code with this target and existing `config.py` / `schemas.py`.

## Key data contracts

- **detection:** `detect_pallets_per_frame(frame) -> List[BBox]` (x1,y1,x2,y2,conf)
- **tracking:** `update(detections)` → `get_tracks()`; `build_pallet_tracks(...) -> List[PalletTrack]`
- **roi:** `crop_roi(bbox, frame, padding_pct, max_side, quality)`; `calculate_blur_score(roi) -> float`
- **view_selection:** `select_views_per_track(track, min_views, target_views, max_views) -> List[PalletObservation]`
- **llm:** `analyze_track(track_id, roi_paths, prompt_profile) -> MinifiedTrackResult`
- **validation:** `enforce_one_product_per_pallet(result) -> bool`; `StrictCountingPolicy.validate(result, track) -> bool`
- **export:** `final_result.json` (OK tracks), `errors.json` (ERROR: MIXED_SKUS, INSUFFICIENT_EVIDENCE)

## Observability (metrics)

Prefer logging/emitting: `tracks_detected`, `tracks_analyzed`, `tracks_ok`, `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence`, `error_rate`, `avg_views_per_track`, `requests_sent`.

## Config (src/config.py)

Settings from env: `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, `EXTRACT_FPS`, `MAX_FRAMES_TO_SEND`, `RESIZE_MAX_SIDE`, `OUTPUT_DIR`, `DEBUG_SAVE_FRAMES`. All thresholds and limits should be configurable via Settings or config files, not literals.
