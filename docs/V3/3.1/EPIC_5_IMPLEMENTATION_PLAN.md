# Epic 5 — Backend implementation plan (exposición en API, revisión y exportaciones)

**Scope:** Backend-only. Expose traceability in API, review, and exports. Epics 1–4 already provide source_image_id, traceability_status, and persistence; Epic 5 adds **optional original_filename** for the source image (US-5.1 / US-5.3) to facilitate review and audit.

**Source of truth:** `docs/V3/3.1/3.1 - Backlog.md` — Épica 5 (Exposición en API, revisión y exportaciones). US-5.1: optionally include original_filename. US-5.3: export CSV/JSON with source_image_id, traceability_status, optionally original_filename.

---

## Interpreted scope of Epic 5

- **Already in place (Epics 2–4):** API entities expose source_image_id, traceability_status, traceability_warning; report and CSV include these; filter by traceability_status exists.
- **Epic 5 addition:** Optional **source_image_original_filename** so that when an entity has source_image_id, consumers can see the original filename of that image (for review/audit and export). This "facilita navegación resultado → imagen" without changing existing contracts.

## Out of scope

- Frontend changes.
- New endpoints or filter types.
- Persistence schema changes (we derive filename from existing manifest at report-build time and optionally at API time from report).

---

## Backend modules touched

| Module | Change |
|--------|--------|
| `src/reporting/hybrid_report.py` | build_hybrid_report accepts optional `source_image_filename_map`; each entity dict gets `source_image_original_filename` when source_image_id is in map. |
| `src/pipeline/stages/reporting_stage.py` | For photos jobs, load job images from manifest, build image_id → original_filename map, pass to build_hybrid_report. |
| `src/api/schemas/responses.py` | EntityListItem: optional `source_image_original_filename`. |
| `src/api/routes/entities.py` | list_entities sets source_image_original_filename from report entity. |
| `src/reporting/artifacts.py` | write_report_csv adds column source_image_original_filename. |
| `tests/test_epic_5.py` | New tests: report/API/CSV include source_image_original_filename when present; legacy without it still works. |

---

## Implementation details

### 1. Report (hybrid_report.py)

- `build_hybrid_report(..., source_image_filename_map: Optional[Dict[str, str]] = None)`.
- For each entity, if `source_image_id` is set and `source_image_filename_map` is provided and `source_image_id` is in the map, set `source_image_original_filename` in the entity dict.

### 2. Reporting stage (reporting_stage.py)

- If `context.job_input.input_type == "photos"`, resolve manifest path via **public** `resolve_manifest_path` from `src.jobs.photos_paths`, load job images via `load_job_images_from_manifest`, build `Dict[str, str]` image_id → original_filename, pass to build_hybrid_report. Otherwise pass None. (Corrections: no private helper from photos_source.)

### 3. API (responses.py, entities.py)

- EntityListItem: `source_image_original_filename: Optional[str] = None`.
- list_entities: set from `e.get("source_image_original_filename")`.

### 4. CSV (artifacts.py)

- Add column `source_image_original_filename`; value from entity dict or empty.

### 5. Tests

- Report: with map, entity gets source_image_original_filename; without map or video job, not set.
- API: response includes source_image_original_filename when in report; legacy report without key still works.
- CSV: column present; value when present, empty when absent.

---

## Backward compatibility

- All new fields optional. Legacy reports and responses without source_image_original_filename remain valid. Video jobs do not have the map; field is omitted or null.

---

## Corrections pass (hardening)

- **Public path helpers:** `src/jobs/photos_paths.py` provides `resolve_manifest_path`, `resolve_photos_dir`, `photos_dir_relative_for_manifest`. ReportingStage and EntityResolutionStage use these; no dependency on private `_resolve_manifest_path` from photos_source. PhotosFrameSource also uses the public helpers.
- **Legacy behavior (Option A):** source_image_original_filename is only guaranteed for reports generated after Epic 5; legacy reports and video jobs return null. Documented in API docstring and EntityListItem field description; no fallback at read time.
- **CSV contract:** Docstrings state that source_image_original_filename is an additive column; empty cell when value missing (video, legacy, or source_image_id not in map).
- **Comments:** hybrid_report and reporting_stage docstrings clarify when the field is set and when it is null; API list_entities documents pass-through and null for legacy.
- **Tests:** Public helper tests, video job (no map), no private helper in reporting_stage, legacy report returns null, CSV column and empty/populated cases.
