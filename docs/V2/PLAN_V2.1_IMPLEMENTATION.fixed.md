# Feature Plan — Version 2.1 Implementation (Revised)

**Source of truth:** `docs/V.2.1.md` (Etapas 2.1.A, 2.1.B, 2.1.D, 2.1.E).

---

## Summary

**Feature:** Redesign the hybrid inventory pipeline to a **structural, label-aware** model (v2.1): one global Gemini call returns **entities** (PALLET | EMPTY_PALLET | LOOSE_BOXES) with position/product label fields and optional label bounding boxes; deterministic **entity ordering** and **pallet_id** resolution (barcode → label text → generated); **count_status** (COUNTED | NEEDS_REVIEW | NOT_COUNTABLE | EMPTY | INVALID_STRUCTURE | COUNTED_MANUAL); **duplicate position_barcode** treated as business conflict (NEEDS_REVIEW, conflict_flag); **entity_quality_score** per entity; **report summary** block (operational KPIs); optional **local barcode hardening** (2.1.B); **evidence pack** with **localized** crops when bbox present, **UNLOCALIZED** when not (2.1.D); **Assisted Counting API** (2.1.E). Visual fallback **disabled for all v2.1** (including NEEDS_REVIEW); use review API instead.

**Scope boundaries:** Same pipeline orchestration (extract frames → one Gemini call → validate → parse → resolve ID → assign status → report). New domain (Entity), new schema and prompt, new report shape. Optional barcode decoder (no OCR stage). Evidence and review are additive (new modules and routes).

---

## Scope & Non-goals

| In scope | Out of scope |
|----------|--------------|
| Entity types PALLET / EMPTY_PALLET / LOOSE_BOXES | New OCR service or external OCR stage |
| Single global Gemini call; schema v2.1 | Increasing number of Gemini calls in baseline |
| Deterministic entity order and pallet_id (barcode → text → generated) | Non-deterministic or ML-based ID |
| count_status and final_quantity rules per entity type | Per-pallet visual fallback in v2.1 (disabled) |
| Duplicate position_barcode → NEEDS_REVIEW + conflict_flag (no auto-suffix) | Auto-suffixing pallet_id on duplicate barcode |
| entity_uid for stable API addressing; entity_quality_score | — |
| Report summary block (KPIs); evidence localization (bbox / UNLOCALIZED) | — |
| Optional local barcode decoding (2.1.B) | Training or fine-tuning models |
| Evidence pack (2.1.D) from existing frames | Per-frame tracking or new detector |
| Review API + resolved report (2.1.E) | Full RBAC / JWT (only actor + audit log) |

---

## Pipeline Placement

- **Detection / tracking:** Unchanged (no per-frame detection; representative frames only).
- **Identification:** Replaced by **one global Gemini call** returning entities (v2.1 schema).
- **Consolidation:** Replaced by **parse_entities → sort_entities_deterministically → resolve_pallet_id → assign_count_status** (no MAD/consolidation across frames).
- **Reporting:** **build_hybrid_report_v2_1** (with summary + entity_quality_score) + optional evidence pack + review merge.

Flow v2.1:

```
Video
  → extract_representative_frames()  [unchanged]
  → Gemini global (entities + labels, optional bboxes)  [new prompt + schema]
  → validate_schema_v2_1  [new]
  → parse_entities()  [new; preserves original index for tie-break]
  → sort_entities_deterministically()  [CRITICAL: before any generated IDs]
  → [2.1.B] barcode_hardening_if_needed()  [optional]
  → resolve_pallet_id()  [new; duplicate barcode → conflict, no suffix]
  → assign_count_status()  [new; respects conflict_flag]
  → compute_entity_quality_score()  [per entity]
  → [Visual fallback DISABLED for v2.1 — all statuses; use review API]
  → [2.1.D] generate_evidence_pack()  [localized if bbox, else UNLOCALIZED]
  → build_hybrid_report_v2_1()  [summary block + entities]
  → write report + evidence_index.json
```

---

## Proposed Design

### Data contracts

- **Gemini response (v2.1):**
  - `total_entities_detected: int`
  - `entities: [{ entity_type, model_entity_id, position_barcode, position_label_text, product_label_text, product_label_quantity, has_boxes, confidence, position_label_bbox?, product_label_bbox? }]`
  - Optional: `position_label_bbox: [x1,y1,x2,y2] | null`, `product_label_bbox: [x1,y1,x2,y2] | null` (normalized 0..1 or pixel coords; spec must fix convention).
- **Domain:** `Entity` dataclass: entity_type, entity_uid (stable: derived from model_entity_id + job_id), pallet_id, pallet_id_method, position_*, product_*, has_boxes, confidence, count_status, final_quantity, conflict_flag, conflict_reason, entity_quality_score; optional bbox fields.
- **Report v2.1:** `mode: "hybrid_v2.1"`, **summary** (total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual), `entities[]` (with count_status, final_quantity, evidence_path, entity_uid, conflict_flag, conflict_reason, entity_quality_score).
- **Evidence index:** `evidence_index.json` with `entities[].evidence` paths and `evidence_localization: "LOCALIZED" | "UNLOCALIZED"`; when UNLOCALIZED, label crop paths absent or marked unavailable.
- **Review record:** JSON per pallet (keyed by entity_uid or pallet_id where unique); action, final_quantity, actor, timestamp, before/after.
- **Resolved report:** Merge of `hybrid_report.json` + review records (overrides applied); summary recounted if needed.

### Interfaces

- `validate_global_analysis_structure_v21(data) -> None` (raises on invalid).
- `parse_entities(data, job_id?) -> List[Entity]` (assigns entity_uid from model_entity_id + job_id; preserves original index for tie-break).
- `sort_entities_deterministically(entities: List[Entity]) -> None` (primary: model_entity_id, secondary: original index).
- `resolve_pallet_id(entities: List[Entity]) -> None` (mutates in place; duplicate position_barcode → both NEEDS_REVIEW, conflict_flag=True, conflict_reason=DUPLICATE_POSITION_BARCODE; no suffix; generated IDs only for entities without position).
- `assign_count_status(entity: Entity) -> None` (sets count_status, final_quantity; if conflict_flag already set, keep NEEDS_REVIEW).
- `compute_entity_quality_score(entity: Entity) -> float` (deterministic formula; mutates entity.entity_quality_score).
- `build_hybrid_report_v2_1(video_path, entities, frames_selected, ...) -> dict` (includes summary block and per-entity fields).
- **2.1.B:** `should_run_barcode_hardening(entity) -> bool`; `barcode_hardening_if_needed(entities, frames, metadata, run_dir) -> BarcodeMetrics`.
- **2.1.D:** `generate_evidence_pack(job_id, run_dir, frames, metadata, entities) -> EvidenceIndex` (uses bbox when present; sets evidence_localization per entity).
- **2.1.E:** `ReviewStore` (load/save by entity_uid/pallet_id); `merge_resolved_report(report, review_store) -> dict`; API uses entity_uid for addressing when pallet_id is duplicated.

### Configuration knobs

- **2.1.A:** (none new beyond existing Gemini/config).
- **2.1.B:** `BARCODE_HARDENING_ENABLED`, `BARCODE_CONSENSUS_MIN_VOTES`, `BARCODE_FORMAT_PREFIX` (or config file), `BARCODE_MAX_ATTEMPTS_PER_ENTITY`.
- **2.1.D:** `EVIDENCE_K_OVERVIEW`, `EVIDENCE_K_POS_CANDIDATES`, `EVIDENCE_K_PROD_CANDIDATES`, `EVIDENCE_MAX_IMAGES_PER_PALLET`, `EVIDENCE_JPEG_QUALITY`.
- **2.1.E:** `REVIEW_STORE=filesystem|db` (or infer from existing SQL Server).

---

## Config / Flags

| Flag / env | Default | Stage | Purpose |
|------------|--------|-------|---------|
| (use existing HYBRID_* / GEMINI_*) | — | A | Unchanged |
| BARCODE_HARDENING_ENABLED | false | B | Enable local barcode decoding |
| BARCODE_CONSENSUS_MIN_VOTES | 2 | B | Min votes to accept decoded barcode |
| EVIDENCE_K_OVERVIEW | 3 | D | Best overview frames per entity |
| EVIDENCE_K_POS_CANDIDATES | 5 | D | Position label candidate crops |
| EVIDENCE_K_PROD_CANDIDATES | 5 | D | Product label candidate crops |
| EVIDENCE_MAX_IMAGES_PER_PALLET | 25 | D | Cap total images per entity |
| EVIDENCE_JPEG_QUALITY | 85 | D | JPEG quality for evidence |
| (review store) | filesystem | E | Where to store review JSON + audit |

---

## Visual fallback policy (v2.1)

- **NOT_COUNTABLE, EMPTY, INVALID_STRUCTURE:** Visual fallback is **disabled**. These statuses mean the system must not invent counts; correction is via review API.
- **NEEDS_REVIEW:** Visual fallback is **disabled** in v2.1. Rationale: avoiding “invented” counts and keeping a single source of truth (label + manual review). Operators use the evidence pack and POST review to set final_quantity.
- **COUNTED:** No fallback needed; quantity comes from product_label_quantity.
- **Implementation:** In the v2.1 pipeline branch, do not call the per-pallet visual fallback at all; remove or bypass the fallback gate for hybrid_v2.1.

---

## Files / Modules Impacted

### Stage 2.1.A

| Area | File / module | Change |
|------|----------------|--------|
| Prompt | `src/llm/global_pallet_analysis_prompt.py` | New prompt v2.1 (entities, entity_type, position_*, product_*, has_boxes, optional position_label_bbox, product_label_bbox) |
| Validation | `src/validation/global_analysis_schema.py` | Add `validate_global_analysis_structure_v21()`; optional bbox fields |
| Parsing | `src/parsing/global_analysis_parser.py` | Add `parse_entities()` → List[Entity], entity_uid, preserve original_index |
| Domain | `src/domain/entity.py` | Entity: entity_uid, conflict_flag, conflict_reason, entity_quality_score, bbox fields |
| Decision | `src/decision/pallet_id.py`, `count_status.py` | resolve_pallet_id (duplicate barcode → conflict, no suffix); assign_count_status; sort_entities_deterministically |
| Reporting | `src/reporting/hybrid_report.py` | build_hybrid_report_v2_1 with **summary** block and entity_quality_score |
| Pipeline | `src/pipeline/hybrid_inventory_pipeline.py` | Wire: parse → sort → resolve_pallet_id → assign_count_status → quality_score; no visual fallback in v2.1 |
| Exceptions | `src/exceptions/global_analysis_exceptions.py` | Add if needed for v21 validation errors |

### Stage 2.1.B

| Area | File / module | Change |
|------|----------------|--------|
| New | `src/barcode/__init__.py` | — |
| New | `src/barcode/policy.py` | `should_run_barcode_hardening(entity) -> bool` |
| New | `src/barcode/decoder.py` | Local decode; use position_label_bbox when present for crops |
| New | `src/barcode/consensus.py` | Vote aggregation, format validation |
| Pipeline | `src/pipeline/hybrid_inventory_pipeline.py` | Call barcode hardening after parse/sort, before resolve_pallet_id |
| Config | `src/config.py` | Barcode-related settings |
| Reporting | `src/reporting/hybrid_report.py` | Include barcode metrics in report |

### Stage 2.1.D

| Area | File / module | Change |
|------|----------------|--------|
| New | `src/evidence/__init__.py` | — |
| New | `src/evidence/evidence_pack.py` | generate_evidence_pack; use position_label_bbox/product_label_bbox for localized crops; else evidence_localization=UNLOCALIZED, overview only |
| New | `src/evidence/scoring.py` | score_frame_sharpness(), dedupe_by_hash() |
| New | `src/evidence/paths.py` | slug(pallet_id) and safe path for entity_uid when needed |
| Pipeline | `src/pipeline/hybrid_inventory_pipeline.py` | Call generate_evidence_pack after report data ready |
| Config | `src/config.py` | K_overview, K_candidates, MAX_IMAGES, JPEG_QUALITY |
| Report | `src/reporting/hybrid_report.py` | evidence_path, evidence_localization per entity |

### Stage 2.1.E

| Area | File / module | Change |
|------|----------------|--------|
| New | `src/api/routes/entities.py` | GET entities (filter by status; identify by entity_uid when pallet_id duplicated), GET evidence, POST review, GET audit |
| New | `src/review/review_store.py` | Load/save by entity_uid (or pallet_id + entity_uid when duplicate); audit log |
| New | `src/review/review_merge.py` | merge_resolved_report(report, reviews); recompute summary counts if needed |
| API | `src/api/server.py` | Register entities router |
| API | `src/api/routes/jobs.py` or entities | GET report?resolved=true |

---

## Task Breakdown (ordered)

### Stage 2.1.A — Structural & label-aware foundation

#### Deterministic entity ordering (CRITICAL)

Before any generated `pallet_id` (PALLET_001, PALLET_002, …) is assigned, entities **must** be sorted deterministically so that the same video + same Gemini response always yields the same ordering and thus the same generated IDs across runs.

- **Sorting rule:**
  - **Primary key:** `model_entity_id` (string), using stable string ordering (e.g. lexicographic).
  - **Tie-breaker:** original JSON order (preserve the index from `parse_entities` as `original_index` and use it when two entities have the same `model_entity_id`, which should be rare).
- **Generated IDs:** Assign PALLET_001, PALLET_002, … only **after** sorting. The counter runs over the sorted list so that entities without position_barcode/position_label_text receive IDs in a fixed order.
- **Why:** Prevents different PALLET_XXX across runs when Gemini returns entities in different order or when parsing order changes.

Tasks and tests below reflect this: sort step before resolve_pallet_id; tests verify that two runs with the same payload produce the same generated IDs.

| # | Task | Complexity | Deps |
|---|------|------------|------|
| A1 | Add `Entity` dataclass in `src/domain/entity.py`: entity_type, entity_uid, pallet_id, pallet_id_method, position_*, product_*, has_boxes, confidence, count_status, final_quantity, conflict_flag, conflict_reason, entity_quality_score, original_index; optional position_label_bbox, product_label_bbox | S | — |
| A2 | New prompt in `global_pallet_analysis_prompt.py` for v2.1: entities array, entity_type, model_entity_id, position_barcode, position_label_text, product_label_text, product_label_quantity, has_boxes, confidence; optionally request position_label_bbox, product_label_bbox [x1,y1,x2,y2] | M | A1 |
| A3 | Add `validate_global_analysis_structure_v21()` in `global_analysis_schema.py` (required keys, types, total_entities_detected == len(entities), confidence in [0,1]; optional bbox arrays length 4) | S | — |
| A4 | Add `parse_entities(data, job_id)` in `global_analysis_parser.py`: raw dict → List[Entity], set entity_uid from model_entity_id + job_id, set original_index from list position; validate per-entity keys and types | M | A1, A3 |
| A4b | Add `sort_entities_deterministically(entities)`: sort by (model_entity_id, original_index); mutate list in place. Call **before** resolve_pallet_id. | S | A4 |
| A5 | Add `resolve_pallet_id(entities)`: 1) position_barcode valid → pallet_id = position_barcode; if duplicate position_barcode across two PALLET entities → set both count_status = NEEDS_REVIEW, conflict_flag = True, conflict_reason = "DUPLICATE_POSITION_BARCODE", keep pallet_id = position_barcode for both (no suffix). 2) Else normalized position_label_text (no duplicate handling beyond barcode). 3) Else assign PALLET_001, PALLET_002, … **in sorted order** (after sort_entities_deterministically). Uniqueness for generated: only one entity per generated id. | M | A4b |
| A6 | Add `assign_count_status(entity)`: EMPTY_PALLET→EMPTY, final_quantity=0; LOOSE_BOXES→INVALID_STRUCTURE; PALLET: if conflict_flag already set keep NEEDS_REVIEW; else position+product_qty→COUNTED; partial→NEEDS_REVIEW; no position no qty→NOT_COUNTABLE | M | A5 |
| A6b | Add `compute_entity_quality_score(entity)`: base = confidence; +0.2 if has position (barcode or label_text); +0.3 if product_label_quantity present; +0.1 if position_barcode from local hardening (2.1.B, flag on entity); clamp [0, 1]. Deterministic. | S | A6 |
| A7 | Add `build_hybrid_report_v2_1()`: mode hybrid_v2.1, **summary** block (total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual), entities with count_status, final_quantity, evidence_path, entity_uid, conflict_flag, conflict_reason, entity_quality_score | M | A6b |
| A8 | Wire pipeline: validate_v21 → parse_entities → sort_entities_deterministically → [2.1.B optional] → resolve_pallet_id → assign_count_status → compute_entity_quality_score; **do not** call visual fallback for v2.1; write report v2.1 | L | A2–A7 |
| A9 | Feature flag or version: HYBRID_VERSION=2.0|2.1; worker and API select path | S | A8 |
| A10 | Tests: schema validation; parse_entities (entity_uid, original_index); sort_entities_deterministically (order stable); resolve_pallet_id (duplicate barcode → conflict, no suffix; generated IDs after sort); assign_count_status (all branches + conflict); entity_quality_score formula; pipeline integration (mock Gemini); **determinism**: same payload → same entity order and same PALLET_XXX | M | A8 |

### Stage 2.1.B — Barcode hardening (optional)

| # | Task | Complexity | Deps |
|---|------|------------|------|
| B1 | Config: BARCODE_HARDENING_ENABLED, BARCODE_CONSENSUS_MIN_VOTES, format validation params | S | — |
| B2 | `src/barcode/policy.py`: should_run_barcode_hardening(entity) — true if PALLET and (position_barcode null/suspicious or low confidence with label hint) | S | A1 |
| B3 | `src/barcode/decoder.py`: select candidate frames (sharpness + dedupe); extract crop using position_label_bbox when present, else heuristic; decode with pyzbar/zxing; return list of (value, symbology, score) | L | B1 |
| B4 | `src/barcode/consensus.py`: group by value, vote, format validation; return best value or conflict/failure | M | B1 |
| B5 | Pipeline: after sort, for each entity run hardening if policy says yes; update entity.position_barcode and pallet_id_method; set flag used by entity_quality_score (+0.1 when barcode from local) | M | A5, B2–B4 |
| B6 | Metrics: barcode_hardening_attempts, success, conflicts, failures; add to report v2.1 | S | B5 |
| B7 | Tests: policy conditions, decoder mock, consensus voting; entity_quality_score includes +0.1 when local barcode set | M | B5 |

### Stage 2.1.D — Evidence pack

| # | Task | Complexity | Deps |
|---|------|------------|------|
| D1 | Config: EVIDENCE_K_OVERVIEW, EVIDENCE_K_POS_CANDIDATES, EVIDENCE_K_PROD_CANDIDATES, EVIDENCE_MAX_IMAGES_PER_PALLET, EVIDENCE_JPEG_QUALITY | S | — |
| D2 | `src/evidence/scoring.py`: score_frame_sharpness (Laplacian), dedupe_by_hash (dHash/pHash), limit list by score + diversity | S | — |
| D3 | `src/evidence/paths.py`: slug(pallet_id) and safe path for entity_uid when needed (e.g. duplicate pallet_id) | S | — |
| D4 | `src/evidence/evidence_pack.py`: per entity, if position_label_bbox/product_label_bbox present, create **localized** crops for position_label and product_label; else set evidence_localization = "UNLOCALIZED", write only overview frames and do not write label crops (or write placeholder/mark unavailable in index). Respect MAX_IMAGES. | L | D1–D3, A1 |
| D5 | Generate evidence_index.json: job_id, mode, entities[].entity_uid, pallet_id, entity_type, count_status, evidence_localization, evidence { overview[], position_label_best, position_label_candidates[], product_label_best, product_label_candidates[] } (candidates absent when UNLOCALIZED) | M | D4 |
| D6 | Pipeline: after assign_count_status + quality_score, call generate_evidence_pack; add evidence_path and evidence_localization to each entity in report | M | A7, D5 |
| D7 | Tests: scoring determinism; path slug; evidence pack structure and limits; **localized**: when bbox present, label crops exist; **unlocalized**: when bbox missing, evidence_localization=UNLOCALIZED, only overview present, label paths absent or marked unavailable; index contract | M | D6 |

### Stage 2.1.E — Assisted counting API

| # | Task | Complexity | Deps |
|---|------|------------|------|
| E1 | `src/review/review_store.py`: load/save review by entity_uid (or composite key when pallet_id duplicated); append audit events (timestamp, actor, action, before, after, notes) | M | — |
| E2 | `src/review/review_merge.py`: merge report + reviews → resolved report; recompute summary (counted_manual, needs_review, etc.) for summary block | M | E1 |
| E3 | GET /api/v1/jobs/{job_id}/entities?status=...&entity_type=...: read report v2.1, filter; include evidence_ref, review status, entity_uid; support lookup by entity_uid for duplicated pallet_id | M | A7, E1 |
| E4 | GET /api/v1/jobs/{job_id}/entities/{entity_uid_or_pallet_id}/evidence: return paths/URLs from evidence_index; when pallet_id is duplicated, require entity_uid for disambiguation | S | D5 |
| E5 | POST /api/v1/jobs/{job_id}/entities/{entity_uid_or_pallet_id}/review: validate body (action, final_quantity, actor, notes); apply SET_COUNT, MARK_EMPTY, etc.; persist by entity_uid; audit log | L | E1 |
| E6 | GET /api/v1/jobs/{job_id}/entities/{entity_uid_or_pallet_id}/audit: return events from review_store | S | E1 |
| E7 | GET /api/v1/jobs/{job_id}/report?resolved=true: return merged report (summary recomputed) | M | E2 |
| E8 | Serve evidence files: static route or signed URL for run/evidence/... | S | E4 |
| E9 | Tests: review store by entity_uid; merge logic and summary recomputation; API status codes and response shape; entity_uid in responses | M | E2–E7 |

---

## Acceptance Criteria

### Stage 2.1.A

- [ ] Gemini returns JSON with total_entities_detected and entities[].entity_type in {PALLET, EMPTY_PALLET, LOOSE_BOXES}; optional position_label_bbox, product_label_bbox.
- [ ] Validation rejects missing keys, wrong types, or total_entities_detected != len(entities).
- [ ] parse_entities produces List[Entity] with entity_uid, original_index, and all required fields.
- [ ] **Deterministic order:** sort_entities_deterministically runs before resolve_pallet_id; same payload → same order and same PALLET_001, PALLET_002, ….
- [ ] resolve_pallet_id: duplicate position_barcode → both entities NEEDS_REVIEW, conflict_flag=True, conflict_reason=DUPLICATE_POSITION_BARCODE; pallet_id remains position_barcode for both (no suffix). Generated IDs only for entities without position, assigned after sort.
- [ ] assign_count_status sets EMPTY/INVALID_STRUCTURE/COUNTED/NEEDS_REVIEW/NOT_COUNTABLE and final_quantity per spec; respects existing conflict_flag.
- [ ] entity_quality_score computed per entity (formula: confidence + 0.2 position + 0.3 product_qty + 0.1 local barcode, clamped [0,1]).
- [ ] Report contains mode hybrid_v2.1, **summary** block (total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual), and entities with count_status, final_quantity, entity_uid, conflict_flag, conflict_reason, entity_quality_score.
- [ ] No extra Gemini calls; **visual fallback not run for any status in v2.1**.
- [ ] Worker and API can run v2.1 vs v2.0 (flag or version).

### Stage 2.1.B

- [ ] When BARCODE_HARDENING_ENABLED and entity needs it, local decoder runs on selected frames/crops (bbox when present).
- [ ] Consensus and format validation gate acceptance; metrics (attempts, success, conflicts) in report.
- [ ] position_barcode and pallet_id updated only when consensus accepts; entity_quality_score reflects +0.1 when barcode from local.

### Stage 2.1.D

- [ ] When bbox present: evidence pack produces **localized** position/product label crops; evidence_localization = "LOCALIZED".
- [ ] When bbox missing: evidence_localization = "UNLOCALIZED"; only overview frames; label crops absent or marked unavailable in index.
- [ ] evidence_index.json includes evidence_localization per entity; image count ≤ EVIDENCE_MAX_IMAGES_PER_PALLET.
- [ ] Report entities include evidence_path and evidence_localization.

### Stage 2.1.E

- [ ] GET entities returns filtered list with evidence_ref, review status, entity_uid; duplicated pallet_id addressable by entity_uid.
- [ ] GET evidence supports entity_uid when pallet_id is duplicated.
- [ ] POST review persists by entity_uid and audit event; idempotent where specified.
- [ ] GET report?resolved=true returns report with overrides and **summary** block updated (e.g. counted_manual).

---

## entity_quality_score (local, deterministic)

- **Purpose:** Sort review queue (e.g. lowest first), dashboards, and filtering without extra Gemini calls.
- **Formula (implementation-oriented):**
  - `base = confidence` (float [0..1] from Gemini).
  - If entity has position (position_barcode or position_label_text non-null and non-empty): `base += 0.2`.
  - If product_label_quantity is not null: `base += 0.3`.
  - If position_barcode was set or confirmed by local hardening (2.1.B): `base += 0.1`.
  - `entity_quality_score = min(1.0, max(0.0, base))`.
- **Deterministic:** Same entity state → same score. No randomness.
- **Tests:** Unit tests for all combinations (no position, no qty → base = confidence; with position and qty and local barcode → cap at 1.0).

---

## Report summary block (required)

The hybrid_report_v2_1 JSON **must** include a top-level **summary** object with the following operational KPIs (counts):

| Field | Type | Description |
|-------|------|-------------|
| total_entities | int | Total number of entities |
| pallets | int | entity_type == PALLET |
| empty_pallets | int | entity_type == EMPTY_PALLET |
| loose_boxes | int | entity_type == LOOSE_BOXES |
| counted | int | count_status == COUNTED |
| needs_review | int | count_status == NEEDS_REVIEW |
| not_countable | int | count_status == NOT_COUNTABLE |
| invalid_structure | int | count_status == INVALID_STRUCTURE |
| counted_manual | int | count_status == COUNTED_MANUAL (after merge with reviews; 0 in base report) |

Summary is computed from the entities array (and, for resolved report, from merged count_status). DoD and acceptance criteria require this block in both base and resolved reports.

---

## Evidence localization requirement

- **Schema (2.1.A):** Optional fields in each entity:
  - `position_label_bbox: [x1, y1, x2, y2] | null`
  - `product_label_bbox: [x1, y1, x2, y2] | null`
  Coordinate convention (e.g. normalized 0..1 or frame pixels) must be fixed in schema doc and prompt.
- **2.1.D behavior:**
  - When **both** (or the relevant) bbox(es) are present and valid: create **localized** crops from those regions; set `evidence_localization = "LOCALIZED"`.
  - When bbox is **missing** or invalid: set `evidence_localization = "UNLOCALIZED"`; generate **only** overview frames; do **not** write position/product label crops (or mark them as unavailable in evidence_index). This avoids misleading crops from heuristics.
- **DoD:** Evidence pack tests cover (1) localized: bbox present → label crops exist and index says LOCALIZED; (2) unlocalized: bbox missing → only overview, evidence_localization=UNLOCALIZED, label paths absent or explicitly unavailable.

---

## Risks & De-risk Plan

| Risk | Mitigation |
|------|------------|
| Gemini mixes text between entities | Strict prompt + schema; validate entity_type; optional cross-checks in tests |
| LOOSE_BOXES misclassified | Clear prompt rules; log low confidence; manual review via 2.1.E |
| Duplicate barcode not surfaced | resolve_pallet_id detects duplicates; set conflict_flag; API uses entity_uid |
| Non-deterministic PALLET_XXX | sort_entities_deterministically before generated IDs; tests with same payload twice |
| Barcode false positives | Consensus (min votes), format validation |
| Evidence storage explosion | Hard limits, dedupe by hash, configurable quality |
| Breaking v2.0 integrations | Version flag; report version field; doc compatibility |
| Review merge bugs | Unit tests for merge and summary recomputation; audit log as source of truth |
| Unlocalized evidence used as label | evidence_localization=UNLOCALIZED; no label crops when bbox missing |

---

## Notes / Open Questions

- **2.1.C** (text extraction improvement): confirm if only prompt tuning.
- **Bbox coordinate convention:** Document in schema whether [x1,y1,x2,y2] is normalized [0,1] or pixel; frame dimensions from metadata.
- **DB for reviews:** If SQL Server is used, store entity_uid; entity_reviews / entity_audit_events tables.
- **Pallet vs Entity:** Add Entity for v2.1; keep Pallet for v2.0 path only.

---

# User Stories Backlog (v2.1)

## Detection / classification

**US-1 — Entity type from Gemini**  
- **Persona:** Backend / integration  
- **Description:** As a system, I need the global Gemini response to include an entity_type per entity so we can apply the correct business rules (PALLET, EMPTY_PALLET, LOOSE_BOXES).  
- **Acceptance criteria:**  
  - **Given** a valid Gemini response for v2.1, **when** we parse it, **then** each entity has entity_type in {PALLET, EMPTY_PALLET, LOOSE_BOXES}.  
  - **Given** an entity_type not in that set, **when** we validate, **then** validation fails with a clear error.  
- **Implementation:** Schema validation in validate_global_analysis_structure_v21; parser maps to Entity.entity_type.

**US-2 — No invented or duplicate entities**  
- **Persona:** Data quality / auditor  
- **Description:** As a system, I must not accept responses where entities are duplicated (same model_entity_id) or where text is invented (null when not visible).  
- **Acceptance criteria:**  
  - **Given** duplicate model_entity_id in entities array, **when** we validate or parse, **then** we reject or dedupe deterministically.  
  - **Given** prompt and schema, **when** we document them, **then** they state “do not invent; use null if not visible”.  
- **Implementation:** Validation of unique model_entity_id; prompt text in global_pallet_analysis_prompt.py.

---

## pallet_id resolution and conflicts

**US-3 — pallet_id from position barcode**  
- **Persona:** Warehouse operator / WMS  
- **Description:** As an integrator, I need pallet_id to be the position barcode when it is present and valid so that it matches WMS/ubicaciones.  
- **Acceptance criteria:**  
  - **Given** an entity with position_barcode non-null and valid (and no duplicate), **when** resolve_pallet_id runs, **then** entity.pallet_id == position_barcode and pallet_id_method == "position_barcode".  
- **Implementation:** resolve_pallet_id() first branch.

**US-4 — pallet_id from position label text when no barcode**  
- **Persona:** Warehouse operator  
- **Description:** When position barcode is missing but position_label_text is present, I need pallet_id to be a normalized form of that text so it is stable and readable.  
- **Acceptance criteria:**  
  - **Given** position_barcode null and position_label_text "POS- 00123 ", **when** resolve_pallet_id runs, **then** pallet_id is normalized and pallet_id_method == "position_label_text".  
- **Implementation:** Normalize function; second branch in resolve_pallet_id.

**US-5 — Generated pallet_id when no position (deterministic)**  
- **Persona:** System / auditor  
- **Description:** When there is no position barcode or text, I need a unique, deterministic generated id (e.g. PALLET_001) so every run produces the same id for the same logical entity.  
- **Acceptance criteria:**  
  - **Given** entities sorted deterministically by model_entity_id then original_index, **when** resolve_pallet_id assigns generated IDs, **then** PALLET_001, PALLET_002, … are stable across runs for the same payload.  
  - **Given** two entities with no position, **when** resolve_pallet_id runs after sort, **then** they get PALLET_001, PALLET_002 with no duplicate.  
- **Implementation:** sort_entities_deterministically() before resolve_pallet_id(); generated IDs assigned in sorted order.

**US-5b — Duplicate position_barcode is business conflict**  
- **Persona:** Operator / auditor  
- **Description:** When two PALLET entities share the same position_barcode, I need both flagged for review and addressable separately, not auto-suffixed.  
- **Acceptance criteria:**  
  - **Given** two entities with the same position_barcode, **when** resolve_pallet_id runs, **then** both have pallet_id = position_barcode, count_status = NEEDS_REVIEW, conflict_flag = true, conflict_reason = "DUPLICATE_POSITION_BARCODE".  
  - **Given** the same job, **when** I call the API, **then** I can address each entity by entity_uid.  
- **Implementation:** resolve_pallet_id() detects duplicate barcode; set conflict_flag/conflict_reason; report and API expose entity_uid.

---

## Schema validation + parsing

**US-6 — Strict schema validation v2.1**  
- **Persona:** Backend developer  
- **Description:** I need the v2.1 global response to be validated for required keys, types, total_entities_detected == len(entities), and optional bbox.  
- **Acceptance criteria:**  
  - **Given** missing "entities" or wrong type, **when** validate_global_analysis_structure_v21 runs, **then** it raises with a clear message.  
  - **Given** total_entities_detected != len(entities), **when** we validate, **then** validation fails.  
  - **Given** optional position_label_bbox with length != 4, **when** we validate, **then** validation fails (or bbox ignored per spec).  
- **Implementation:** global_analysis_schema.py validate_global_analysis_structure_v21.

**US-7 — Parse to Entity list**  
- **Persona:** Backend developer  
- **Description:** I need a single function that maps the validated JSON to a list of Entity domain objects with entity_uid and original_index.  
- **Acceptance criteria:**  
  - **Given** valid v2.1 JSON and job_id, **when** parse_entities runs, **then** we get List[Entity] with entity_uid (e.g. f"{job_id}_{model_entity_id}") and original_index set.  
  - **Given** an entity with product_label_quantity as string "15", **when** we parse, **then** we coerce to int or fail validation.  
- **Implementation:** parse_entities() in global_analysis_parser.py.

---

## Report summary and entity_quality_score

**US-7b — Report summary (KPIs)**  
- **Persona:** Ops / dashboard  
- **Description:** I need the report to include a summary block with counts (total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual) so I can monitor KPIs without scanning entities.  
- **Acceptance criteria:**  
  - **Given** a v2.1 report, **when** I read it, **then** top-level "summary" exists with all listed fields.  
  - **Given** resolved=true report, **when** a review set count_status to COUNTED_MANUAL, **then** summary.counted_manual reflects it.  
- **Implementation:** build_hybrid_report_v2_1() computes summary from entities; merge_resolved_report() recomputes summary.

**US-7c — entity_quality_score**  
- **Persona:** Operator / dashboard  
- **Description:** I need a per-entity quality score [0..1] (confidence + position + product qty + local barcode) so I can sort the review queue (e.g. lowest first) or filter.  
- **Acceptance criteria:**  
  - **Given** an entity with confidence 0.5, position present, product_label_quantity present, **when** we compute entity_quality_score, **then** score = min(1, 0.5 + 0.2 + 0.3) = 1.0.  
  - **Given** same entity and barcode from local hardening, **when** we compute, **then** score includes +0.1 (capped at 1).  
- **Implementation:** compute_entity_quality_score(); formula in plan; tests for all branches.

---

## Evidence pack generation

**US-8 — Overview and localized label crops**  
- **Persona:** Operator / reviewer  
- **Description:** I need the evidence pack to include overview frames and, when bbox is available, localized label crops so I can verify labels.  
- **Acceptance criteria:**  
  - **Given** entity with position_label_bbox and product_label_bbox, **when** we generate evidence, **then** evidence_localization = LOCALIZED and label crops exist.  
  - **Given** entity without bbox, **when** we generate evidence, **then** evidence_localization = UNLOCALIZED; only overview; no label crops (or marked unavailable).  
- **Implementation:** evidence_pack.py uses bbox when present; else UNLOCALIZED and overview only.

**US-9 — Evidence index contract**  
- **Persona:** Frontend / API consumer  
- **Description:** I need a stable JSON index (evidence_index.json) with evidence_localization and per-entity paths (overview; label when LOCALIZED).  
- **Acceptance criteria:**  
  - **Given** a completed job with evidence, **when** I read run/evidence_index.json, **then** each entity has evidence.overview, evidence_localization, and label paths only when LOCALIZED.  
  - **Given** slug(pallet_id) or entity_uid for paths, **when** we write paths, **then** paths are filesystem-safe.  
- **Implementation:** evidence_pack.py writes evidence_index.json; paths.py slug().

---

## Review API endpoints

**US-10 — List entities with optional filter**  
- **Persona:** Operator / UI  
- **Description:** I need to call an API to list entities of a job, optionally filtered by status or entity_type, with entity_uid for disambiguation when pallet_id is duplicated.  
- **Acceptance criteria:**  
  - **Given** job_id and optional query status=NEEDS_REVIEW, **when** GET entities runs, **then** response contains entities array with pallet_id, count_status, evidence_ref, review.status, entity_uid.  
- **Implementation:** entities.py GET entities; read report + review store.

**US-11 — Submit manual count override**  
- **Persona:** Operator  
- **Description:** I need to POST a manual count (or mark empty/invalid) for an entity (by entity_uid when pallet_id is duplicated) so the resolved report reflects human correction.  
- **Acceptance criteria:**  
  - **Given** job_id, entity_uid (or pallet_id when unique), body { action: "SET_COUNT", final_quantity: 15, actor: "op1" }, **when** POST review runs, **then** review is saved and audit event appended; GET report?resolved=true shows final_quantity 15 and count_status COUNTED_MANUAL.  
  - **Given** invalid action or entity not in job, **when** POST review runs, **then** 400 or 404 with clear message.  
- **Implementation:** entities.py POST review; review_store by entity_uid; review_merge applied.

---

## Resolved report + audit

**US-12 — Resolved report and audit trail**  
- **Persona:** Auditor / operator  
- **Description:** I need a “resolved” report that merges original result with review overrides and updated summary, and an audit log per entity.  
- **Acceptance criteria:**  
  - **Given** job has one review (SET_COUNT for entity_uid E1), **when** GET report?resolved=true, **then** that entity shows final_quantity and count_status from review and summary.counted_manual >= 1.  
  - **Given** same job, **when** GET entities/{E1}/audit, **then** response includes events with timestamp, actor, action, before, after.  
- **Implementation:** review_merge.merge_resolved_report(); GET audit from review_store.

---

## Metrics (basic)

**US-13 — Barcode and evidence metrics in report**  
- **Persona:** Ops / analytics  
- **Description:** I need the report to include summary KPIs and barcode metrics (attempts, success, conflicts) so we can monitor quality.  
- **Acceptance criteria:**  
  - **Given** 2.1.B ran, **when** I read report, **then** metrics include barcode_hardening_attempts, barcode_hardening_success (and conflicts/failures if present).  
  - **Given** 2.1.D ran, **when** I read report and evidence_index, **then** I can derive per-entity image counts and evidence_localization.  
- **Implementation:** Summary block in report; barcode module returns BarcodeMetrics; evidence_localization in index.

---

# File / Folder Structure Changes

```
New files:
  src/domain/entity.py              # Entity dataclass (v2.1): entity_uid, conflict_*, quality_score, bbox
  src/decision/pallet_id.py         # resolve_pallet_id() (duplicate → conflict, no suffix)
  src/decision/count_status.py     # assign_count_status()
  src/decision/entity_order.py     # sort_entities_deterministically()
  src/decision/quality_score.py    # compute_entity_quality_score()
  src/barcode/__init__.py
  src/barcode/policy.py
  src/barcode/decoder.py
  src/barcode/consensus.py
  src/evidence/__init__.py
  src/evidence/evidence_pack.py    # localized vs UNLOCALIZED
  src/evidence/scoring.py
  src/evidence/paths.py
  src/review/__init__.py
  src/review/review_store.py       # by entity_uid
  src/review/review_merge.py       # merge + summary recompute
  src/api/routes/entities.py      # entity_uid for disambiguation

Modified files:
  src/llm/global_pallet_analysis_prompt.py   # v2.1 prompt + optional bbox
  src/validation/global_analysis_schema.py   # v21 validation + optional bbox
  src/parsing/global_analysis_parser.py      # parse_entities(), entity_uid, original_index
  src/domain/__init__.py                     # export Entity
  src/reporting/hybrid_report.py             # build_hybrid_report_v2_1() + summary block
  src/pipeline/hybrid_inventory_pipeline.py  # sort → resolve → quality_score; no fallback v2.1
  src/api/server.py                         # register entities router
  src/config.py                             # new settings (B, D, E)
  src/jobs/worker.py                        # optional: pass version
  src/api/routes/jobs.py                    # report?resolved=
```

Optional: keep `src/domain/pallet.py` and v2.0 path when HYBRID_VERSION=2.0.

---

# Definition of Done — v2.1 Release

- [ ] **2.1.A:** All A acceptance criteria met. **Deterministic ordering:** sort before generated IDs; same payload → same PALLET_XXX. **Duplicate barcode:** conflict_flag, conflict_reason, no suffix; entity_uid in report. **Summary block** in report. **entity_quality_score** per entity (formula + tests). **Visual fallback:** disabled for all v2.1 statuses. Tests: schema, parse, sort, resolve_pallet_id (including duplicate case), assign_count_status, quality_score, pipeline.
- [ ] **2.1.B:** Policy + decoder + consensus; use bbox when present; config flags; metrics in report; entity_quality_score +0.1 when local barcode; tests with mock decoder; no new Gemini calls.
- [ ] **2.1.D:** Evidence: **localized** when bbox present (label crops); **UNLOCALIZED** when bbox missing (overview only, label paths absent/unavailable). evidence_index.json with evidence_localization. Limits and dedupe. Tests: localized and unlocalized flows.
- [ ] **2.1.E:** GET entities (entity_uid, filter); GET evidence (entity_uid when duplicated); POST review (by entity_uid); GET audit; GET report?resolved=true (summary recomputed). Review store (filesystem MVP) and merge logic; audit log. Tests: API and merge.
- [ ] **Docs:** HYBRID_MODE.md or new doc updated for v2.1; V.2.1.md referenced; env/config and bbox convention documented.
- [ ] **Compatibility:** v2.0 path still runnable (flag or version); report version field; no breaking change to v2.0 job result shape.
- [ ] **Code quality:** No hardcoded thresholds (config); determinism where specified; minimal logging.

---

# Migration / Compatibility

- **Report shape:** v2.0 has `mode: "hybrid"`, `pallets[]`, `frames_selected`. v2.1 has `mode: "hybrid_v2.1"`, **summary** (total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual), `entities[]` (entity_uid, count_status, conflict_flag, conflict_reason, entity_quality_score, evidence_path, evidence_localization). Add top-level `report_version: "2.0" | "2.1"`.
- **API:** When job is v2.1, return v2.1 report and support entity_uid for duplicated pallet_id. When job is v2.0, return current format.
- **DB (Stage 8):** Extend or add entity_results with entity_uid, entity_type, count_status, conflict_flag; keep pallet_results for v2.0.
- **Integrations:** Document v2.1 report shape (summary + entities); consumers that need a flat pallet list can map entities (e.g. PALLET only) and use entity_uid where pallet_id is duplicated.
- **Feature flag:** `HYBRID_VERSION=2.1` (default) or `2.0`.

---

# Changelog vs original plan

- **Deterministic entity ordering:** Added dedicated subsection "Deterministic entity ordering (CRITICAL)" in Stage 2.1.A: sort by model_entity_id (primary), original_index (tie-breaker); generated IDs assigned only after sort. Added task A4b (sort_entities_deterministically); updated A5 to reference sort; A10 tests include determinism (same payload → same PALLET_XXX). Pipeline and data contracts updated.
- **Duplicate position_barcode = business conflict:** Removed auto-suffix for duplicate barcode. Both entities get count_status = NEEDS_REVIEW, conflict_flag = true, conflict_reason = "DUPLICATE_POSITION_BARCODE"; pallet_id = position_barcode for both. Introduced entity_uid (model_entity_id + job_id) as stable internal key for API addressing. Updated schema/report (entity_uid, conflict_flag, conflict_reason); resolve_pallet_id logic and tasks (A5, A10); user story US-5b; E3/E4/E5 to use entity_uid when pallet_id duplicated; review store and merge keyed by entity_uid.
- **Report summary metrics:** Added required "summary" block to hybrid_report_v2_1: total_entities, pallets, empty_pallets, loose_boxes, counted, needs_review, not_countable, invalid_structure, counted_manual. New subsection "Report summary block (required)"; task A7 and build_hybrid_report_v2_1 updated; acceptance criteria and DoD updated; E2 and merge_resolved_report recompute summary; user story US-7b.
- **entity_quality_score:** Added locally computed score [0..1]: base = confidence; +0.2 if has position; +0.3 if product_label_quantity present; +0.1 if barcode from local hardening (2.1.B); clamp [0,1]. New subsection "entity_quality_score (local computed)" with formula and use (review queue, dashboards). Entity dataclass and report include entity_quality_score; task A6b and A10 tests; user story US-7c; B7 tests for +0.1 when local barcode.
- **Evidence localization:** Schema 2.1.A extended with optional position_label_bbox, product_label_bbox [x1,y1,x2,y2] | null. Stage 2.1.D: use bboxes for localized crops; when bbox missing set evidence_localization = "UNLOCALIZED", only overview frames, label crops absent or marked unavailable. New subsection "Evidence localization requirement"; tasks D4, D5, D7; acceptance criteria and DoD for localized and unlocalized flows; user stories US-8, US-9 updated.
- **Visual fallback policy:** New subsection "Visual fallback policy (v2.1)": disabled for NOT_COUNTABLE, EMPTY, INVALID_STRUCTURE; **disabled for NEEDS_REVIEW** (recommended: use review API instead of invented counts). Pipeline and acceptance criteria updated to state no visual fallback for any v2.1 status.
- **Misc:** Pipeline flow diagram updated (sort step, no fallback). Interfaces and data contracts updated (entity_uid, conflict_*, summary, entity_quality_score, bbox, evidence_localization). File structure adds entity_order.py, quality_score.py; review_store and merge use entity_uid.
