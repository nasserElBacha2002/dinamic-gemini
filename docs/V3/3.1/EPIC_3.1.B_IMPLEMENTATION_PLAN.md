# Epic 3.1.B — Backend Implementation Plan

**Scope:** Backend-only. Parse and validate `source_image_id` from provider responses; normalize traceability state; persist and expose in backend contracts.

**Source of truth:** `docs/V3/3.1/3.1 - Backlog.md` (Épica 3, 4, 5 partial), `docs/V3/3.1/3.1 Documento tecnico.md`.

---

## Phase 1 — Analysis summary

### Where provider responses are parsed

- **Gemini:** Returns JSON validated by `GlobalEntityResponseV21` (Pydantic) in `src/llm/gemini_global_analyzer.py`; then `validate_global_analysis_structure_v21` in `src/validation/global_analysis_schema.py`; then `parse_entities(data, job_id)` in `src/parsing/global_analysis_parser.py` builds `List[Entity]`.
- **Entity:** Domain model in `src/domain/entity.py` (dataclass). No traceability fields yet.

### Where results are normalized and persisted

- **Entity resolution:** `EntityResolutionStage` in `src/pipeline/stages/entity_resolution_stage.py` runs `parse_entities` then sort, resolve_pallet_id, assign_count_status, compute_entity_quality_score.
- **Report:** `build_hybrid_report` in `src/reporting/hybrid_report.py` builds a dict from `List[Entity]`; written to `run_dir/hybrid_report.json` by reporting stage.
- **DB:** `_push_success_to_db` in `src/jobs/worker.py` reads report, builds `pallets_list` from entities, calls `PalletResultsRepository.insert_pallet_results(job_id, pallets_list)`.

### Epic 3.1.A image identity

- **Valid image IDs:** From manifest via `load_job_images_from_manifest(manifest_path, photos_dir_rel)` in `src/jobs/image_identity.py`; returns `List[JobImage]`. Set of valid IDs = `{img.image_id for img in images}`.
- **When available:** Only for photos jobs; manifest path from `context.job_input.input_manifest_path` and `photos_dir`; same resolution as in `GeminiAnalysisProvider`.

### Integration points for Epic B

1. **Schema (EntityV21):** Add optional `source_image_id: Optional[str] = None` so provider can return it (Gemini Structured Output allows it).
2. **Parser:** In `parse_entities`, read `source_image_id` from each entity dict; set on `Entity`. Do not validate yet (no valid_image_ids in parser).
3. **Traceability validation:** New function `apply_traceability_validation(entities, valid_image_ids: frozenset)` in a dedicated module; sets `traceability_status` and `traceability_warning` on each entity.
4. **EntityResolutionStage:** After `parse_entities`, if photos job load manifest and get valid_image_ids; call `apply_traceability_validation(entities, valid_image_ids)`.
5. **Entity domain:** Add `source_image_id: Optional[str]`, `traceability_status: Optional[str]`, `traceability_warning: Optional[str]`.
6. **Report:** Include the three fields in each entity dict in `build_hybrid_report`.
7. **Worker/DB:** Add `source_image_id` and `traceability_status` to each item in `pallets_list`; extend `insert_pallet_results` and `get_pallet_results` when table has columns (migration snippet provided).
8. **API:** Extend `EntityListItem` and list_entities to expose `source_image_id` and `traceability_status`.

---

## Phase 2–7 — File and responsibility list

| File | Change |
|------|--------|
| `src/domain/entity.py` | Add `source_image_id`, `traceability_status`, `traceability_warning`. |
| `src/domain/traceability.py` (new) | `TraceabilityStatus` Literal; `apply_traceability_validation(entities, valid_image_ids)`. |
| `src/models/schemas.py` | Add `source_image_id: Optional[str] = None` to `EntityV21`. |
| `src/parsing/global_analysis_parser.py` | In `parse_entities`, set `source_image_id` from `e.get("source_image_id")`. |
| `src/pipeline/stages/entity_resolution_stage.py` | Load job images for photos jobs; call `apply_traceability_validation`. |
| `src/reporting/hybrid_report.py` | Add traceability fields to entity_dicts. |
| `src/jobs/worker.py` | Add `source_image_id`, `traceability_status` to pallets_list. |
| `src/database/repository.py` | Add optional columns to insert_pallet_results / get_pallet_results; document migration. |
| `src/api/schemas/responses.py` | Add `source_image_id`, `traceability_status` to `EntityListItem`. |
| `src/api/routes/entities.py` | Pass through new fields when building EntityListItem. |
| `docs/V3/3.1/migrations/pallet_results_traceability.sql` (new) | Optional ALTER TABLE for DB. |
| `tests/test_epic_3_1_b.py` (new) | Tests for parsing, validation, report, compatibility. |

---

## Traceability status rules

- `valid`: `source_image_id` is present and in `valid_image_ids` (context was available).
- `missing`: `source_image_id` is absent or empty.
- `invalid`: `source_image_id` is present but not in `valid_image_ids` (context was available); warning set.
- `unvalidated`: `source_image_id` is present but validation context was not available (e.g. video job, manifest missing). Used to avoid false negatives; we do not mark as invalid when context could not be established.

When `valid_image_ids` is empty, do **not** treat non-empty `source_image_id` as invalid; use `unvalidated` instead.

---

## Hardening (corrections pass)

- **Validation semantics:** When validation context is missing (empty `valid_image_ids`), use status `unvalidated` for present `source_image_id`; do not mark as invalid.
- **Typing:** `TraceabilityStatus` enum (valid, missing, invalid, unvalidated); `TraceabilityStatusLiteral` in API; entity/report store string values.
- **Persistence semantics:** Each `pallet_results` row = one pipeline entity; `source_image_id` = single source image for that entity. Documented in repository and schema.sql.
- **traceability_warning:** Diagnostic only — report and API; **not** persisted to `pallet_results`. Documented in entity, report, worker, and DTO.
- **Manifest path:** Entity resolution stage reuses `_resolve_manifest_path` from `photos_source` for consistent path resolution.
- **Parser:** `source_image_id` normalized via `_safe_str` (strip, empty→None); contract documented in `parse_entities` docstring.
- **DB:** Allowed status values application-enforced; no CHECK constraint to keep migrations safe (documented in schema.sql).

---

## Backward compatibility

- Legacy provider responses without `source_image_id`: parser sets `source_image_id=None`; validation sets `traceability_status="missing"`.
- Report and API: new fields optional; consumers that ignore them unchanged.
- DB: new columns nullable; migration in `src/database/schema.sql` (IF NOT EXISTS ADD source_image_id, traceability_status).

---

## Left for Epic 3.1.C

- Frontend screens / visual review flows.
- Advanced filtering UI, metrics dashboards.
- Full multi-evidence (`source_image_ids`, `primary_image_id`).
- Evidence-quality scoring.
- Any advanced exports beyond backend contract parity.
