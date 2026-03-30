# Inventory V3 Data Duplication Audit

**Audit date:** 2026-03-30  
**Scope:** Backend v3 inventories / aisles / positions / evidences / review / CSV export + relevant frontend API types.  
**Method:** Code trace (schemas → mappers → domain → SQL → pipeline mapper → export).

---

## 1. Executive summary

The v3 inventory surface deliberately carries **three overlapping layers** at once:

1. **Persisted domain** (`positions`, `product_records`, `evidences`, `review_actions`) — normalized tables.
2. **Pipeline snapshot** (`positions.detected_summary_json`) — a JSON projection of `hybrid_report.json` entities plus quantity-resolution metadata and audit flags.
3. **Operator / SPA contract** — flattened fields on `PositionSummaryResponse` (`sku`, `qty`, `qtySource`, traceability, `has_evidence`, etc.) plus the **entire** `detected_summary_json` blob still returned for backward compatibility.

The **most risky duplications** are:

| Risk | Why |
|------|-----|
| **Quantity tripled** | The same resolved quantity and provenance effectively live in `product_records`, again inside `detected_summary_json` (`final_quantity` / `qty_*` keys), and again as API fields (`qty`, `qtySource`, `detected_quantity`). Legacy paths and consolidation can expose **stale** summary numbers vs `ProductRecord` unless mappers align them (see `position_to_summary`). |
| **SKU / identity multiplied** | Public `sku` is derived from summary fallbacks (`internal_code` → `review_display_label` → `position_barcode` → `pallet_id`) while `product_records.sku` is authoritative in DB; CSV adds **`sku` + `internal_code` + `barcode`** — easy to diverge mentally and in exports. |
| **Evidence vs image identity** | `primary_evidence_id` (column), `has_evidence` (derived), `evidences[].is_primary` (detail), and `source_image_id` / `source_image_original_filename` (summary + optional enrichment from `hybrid_report.json`) are **related but not the same** — naming suggests duplication; semantically they are different links (crop vs source photo). |
| **`detected_summary_json` as God-object** | It mixes pipeline fields, quantity-resolution output, consolidation artifacts (`aggregated_from_ids`), and `_audit`. Exposing it **and** flattening selected keys duplicates semantics and encourages clients to “prefer JSON” vs “prefer API contract” inconsistently. |
| **Naming / casing split** | Position API uses **camelCase** for quantity contract (`qtySource`, `qtyInferenceReason`, `qtyResolved`); CSV uses **snake_case** (`qty_source`, `qty_inference_reason`). Same concepts, different shapes. |

**Overall severity:** **Medium–High** for long-term maintainability and client confusion; **Lower** for immediate data loss (single writer pipeline + explicit mapper rules reduce random divergence).

---

## 2. Scope reviewed

### Files reviewed (representative)

- **API schemas:** `backend/src/api/schemas/position_schemas.py`, `inventory_schemas.py`, `aisle_schemas.py`, `review_queue_schemas.py`
- **Mappers / routes:** `backend/src/api/routes/v3/shared.py` (`position_to_summary`, `_summary_sku_and_quantity_from_position`, `_qty_contract_from_product`, `_resolve_qty_contract_from_position_legacy`, traceability enrichment), `backend/src/api/routes/v3/positions.py`, `inventories.py`, `aisles.py`
- **Pipeline → domain:** `backend/src/infrastructure/pipeline/v3_report_mapper.py` (`_detected_summary`, `_qty_from_entity`, `map_hybrid_report_to_domain`)
- **Quantity logic:** `backend/src/domain/quantity/resolution.py` (referenced from mapper + `shared.py`)
- **Consolidation:** `backend/src/application/services/position_sku_consolidation.py`
- **Domain:** `backend/src/domain/positions/entities.py`, `backend/src/domain/products/entities.py`, `backend/src/domain/evidence/entities.py`
- **Persistence:** `backend/src/database/schema.sql` (positions, product_records, evidences, review_actions, aisles, inventories, jobs), `backend/src/infrastructure/repositories/sql_position_repository.py`, `sql_product_record_repository.py`
- **CSV:** `backend/src/application/use_cases/export_inventory_results.py`, `backend/src/application/mappers/inventory_export_rows.py`, `backend/src/application/services/csv_inventory_exporter.py`
- **Analytics SQL (summary usage):** `backend/src/infrastructure/repositories/sql_analytics_repository.py` (reads `JSON_VALUE(detected_summary_json, ...)`)
- **Frontend contract:** `frontend/src/api/types/responses.ts` (`PositionSummary`, `PositionDetailResponse`)

### Entities / tables

- `inventories`, `aisles`, `positions`, `product_records`, `evidences`, `review_actions`, `source_assets`, `inventory_jobs` / job tables as applicable, `raw_labels` (pipeline normalization — not fully traced in this audit)

### Endpoints (explicit)

- `GET /api/v3/inventories`, `GET /api/v3/inventories/{inventory_id}`
- `GET /api/v3/inventories/{inventory_id}/aisles`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`
- CSV via export use case (wired from API route — same row builder as parity comment in code)

### Exports

- `CsvInventoryExporter.INVENTORY_RESULTS_CSV_FIELDS` + `position_to_export_row_dict`

---

## 3. Field duplication matrix

Abbreviations: **SoT** = source of truth, **Pub** = public API, **Int** = internal / technical, **Der** = derived at read time.

| Field / Concept | Where it appears | SoT (today) | Pub / Int / Der | Duplication type | Risk | Recommendation |
|-----------------|------------------|-------------|-----------------|------------------|------|----------------|
| **Position lifecycle `status`** | `positions.status`, API `PositionSummary.status` | DB column | Pub (canonical) | Acceptable mirror | Low | Keep; document enum once. |
| **`needs_review`** | `positions.needs_review`, API, CSV | DB (+ pipeline sets initial) | Pub | Acceptable mirror | Low | Keep. |
| **`count_status`** | Inside `detected_summary_json` only | Pipeline entity | Int (in blob) | Semantic distinct from position `status` | Med | Rename in docs to “pipeline count outcome”; don’t conflate with `PositionStatus`. |
| **SKU shown in list (`sku`)** | API `PositionSummary.sku`, CSV `sku` | **Derived** from `detected_summary_json` via `_summary_sku_and_quantity_from_position` | Der | Semantic overlap with `internal_code` / fallbacks | **High** | Treat **`product_records.sku`** as SoT for display when primary exists; derive `sku` from primary + single fallback rule; deprecate multi-key fallback in public contract. |
| **`internal_code`** | Pipeline entity → summary JSON; CSV column | Pipeline snapshot in JSON | Int→Pub (CSV duplicates API) | Literal vs `sku` | **High** | CSV: keep one canonical “product id” column; move `internal_code` to optional debug export. |
| **`review_display_label`** | `detected_summary_json` | Pipeline | Int (blob) | Semantic: display / label text | Med | Keep in blob or expose as single optional `product_label` on API; avoid duplicating as second `sku`. |
| **`position_barcode`** | Summary JSON | Pipeline | Int | Semantic overlap with barcode | Med | Same as above; align with one “barcode” field in public contract. |
| **Barcode in CSV** | `barcode` from `position_barcode` in summary | JSON | Pub (CSV) | Duplicates summary + overlaps `sku` | Med | Derive from same SoT as API. |
| **Quantity final (operator)** | API `qty`, CSV `final_quantity` | **`ProductRecord`** when primary exists + mapper; else legacy from summary | Pub | Semantic: multiple underlying fields | **High** | Document: **`qty` = authoritative display quantity**; stop also shipping redundant `detected_quantity` when `qty` is mandatory. |
| **`detected_quantity` (API)** | `PositionSummary.detected_quantity` | Aligned to `qty` when primary exists; else from summary | Pub | **Duplicates `qty` in most paths** | **High** | Deprecate or redefine strictly as “pre-review detected” vs final; v3.2.2 comment says aligned to avoid stale summary. |
| **`final_quantity` (JSON)** | `detected_summary_json.final_quantity` | Pipeline | Int (snapshot) | Duplicates `product_records.detected_quantity` after map | **High** | Treat as **immutable pipeline snapshot**; don’t use for new business rules; API should prefer `ProductRecord`. |
| **`product_label_quantity`** | Summary JSON | Pipeline | Int | Semantic alt input to resolver | Med | Keep internal; don’t expose separately in CSV. |
| **`qty_final`, `max_qty`…** | Summary JSON (`qty_meta` from `_qty_from_entity`) | Computed at ingest | Int in JSON | Duplicates numeric in `product_records` | **High** | Mark as technical snapshot only; optionally strip from Pub blob in v4. |
| **`qty_source` (DB)** | `product_records.qty_source` | Persisted | Int + CSV (snake) | Differs from API `qtySource` (camel) **same concept** | Med | Unify naming in one public layer (versioned). |
| **`qty_inference_reason`** | DB + summary JSON + API `qtyInferenceReason` | `ProductRecord` wins when primary set | Pub | Literal duplicate across layers | Med | Single SoT: `ProductRecord`; JSON copy for audit only. |
| **`qty_is_resolved` vs `qtyResolved`** | Summary vs API | Legacy path reads JSON; product path maps to contract | Pub | camelCase vs snake in CSV | Med | One naming convention per surface. |
| **`raw_qty`, `qty_parse_status`, `qty_origin_field`** | Summary JSON + `product_records.raw_qty_json`, `qty_parse_status` | Dual persist | Int | **Literal duplication** | **High** | Prefer DB columns; keep JSON only if needed for cold replay of pipeline. |
| **`primary_evidence_id`** | `positions` column, API, CSV | DB | Pub | Mirror | Low | Keep. |
| **`has_evidence`** | API `PositionSummary.has_evidence` | **Derived** `bool(primary_evidence_id)` | Der | Semantic duplicate of primary flag | Low | Acceptable UX denormalization; document. |
| **`source_image_id`** | Summary JSON + hybrid_report enrichment + API + CSV | Enriched from entity; fallback load report | Pub | Overlaps **evidence** conceptually | **High** | Document: **photo-level traceability**, not `evidences.id`. |
| **`source_image_original_filename`** | Summary + enrichment + API | Same | Pub | Duplicate channel vs `source_image_id` | Low | Acceptable. |
| **`traceability_status`** | Summary + API + CSV + analytics SQL | Summary / entity | Pub | Mirror | Low–Med | Keep single definition (`valid` / `invalid` / …). |
| **`corrected_quantity`** | `product_records`, API, CSV | DB | Pub | CSV also maps to `final_quantity` | Med | Document CSV rule: `final_quantity = corrected ?? qty`. |
| **`ProductRecord` list on detail** | Removed from `PositionDetailResponse` (v3.1.1) | N/A | — | Reduces duplication in one endpoint | — | Good; duplication shifted to summary+summary JSON only. |

---

## 4. Findings by area

### 4.1 API contracts

- **`PositionSummaryResponse`** (`position_schemas.py`) combines:
  - Columns: `id`, `aisle_id`, `status`, `confidence`, `needs_review`, `primary_evidence_id`, timestamps.
  - **Full** `detected_summary_json` (optional dict).
  - Flattened commerce fields: `sku`, `detected_quantity`, `corrected_quantity`, `qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved`.
  - Traceability: `source_image_id`, `traceability_status`, `source_image_original_filename`, `has_evidence`.
- **List vs detail:** Both use the **same** `position_to_summary` mapper with the same `primary_product` selection rule (`select_display_primary_product`) — **good for consistency**; remaining divergence is consolidation + legacy rows without `qty_source`.
- **CamelCase contract:** `qtySource`, `qtyInferenceReason`, `qtyResolved` — frontend mirrors in `PositionSummary` (`responses.ts`).

### 4.2 Position payloads

- **Authoritative path:** `position_to_summary(..., primary_product=...)` uses `_qty_contract_from_product` when `primary_product.qty_source` is set; when `qty_source` empty, uses `detected_quantity` from record with public `qtySource="detected"` and `qtyResolved=None` (legacy).
- **Aggregated rows (v3.2.3):** When `aggregated_from_ids` present in summary, mapper **overrides** quantity contract from summary totals and sets `qtySource="detected"` — `ProductRecord` may not reflect consolidation; comment in code acknowledges this.
- **Legacy path:** `_resolve_qty_contract_from_position_legacy` reads **either** structured `qty_final` + `qty_source` from summary **or** recomputes from `final_quantity` / `product_label_quantity` + `count_status` / `entity_type` / evidence flags.

### 4.3 Detected summary JSON

- **Writer:** `v3_report_mapper._detected_summary` copies entity fields (`entity_uid`, `entity_type`, `pallet_id`, `internal_code`, `final_quantity`, `product_label_quantity`, `count_status`, barcodes, labels, traceability, filenames) + optional `_audit`.
- **Quantity meta:** `_qty_from_entity` merges **resolved quantity** into the same dict: `qty_final`, `qty_source`, `qty_inference_reason`, `raw_qty`, `qty_parse_status`, `qty_origin_field`, `qty_is_resolved`.
- **Comment in code:** *“Secondary projection in detected_summary_json; ProductRecord is authoritative.”* — this is the intended SoT split, but the API still exposes both.

### 4.4 Persistence / DB

- **`positions`:** Core row + `detected_summary_json` + `corrected_summary_json` (latter not traced deeply in this audit).
- **`product_records`:** `sku`, `detected_quantity`, `corrected_quantity`, `qty_source`, `qty_inference_reason`, `raw_qty_json`, `qty_parse_status` — **canonical post-map state**.
- **Duplication:** Same resolution outputs are **also** embedded in `detected_summary_json` at ingest time. Risk: **post-review updates** (e.g. SKU update use case) may fix `product_records` / summary partially — see `update_product_sku.py` (mentions keeping `detected_summary_json.internal_code` coherent).

### 4.5 CSV export

- **Builder:** `inventory_export_rows.position_to_export_row_dict` calls **`position_to_summary`** — explicitly aims for API parity.
- **Columns:** `sku`, `product_label`, `barcode`, `internal_code`, `detected_quantity`, `corrected_quantity`, `final_quantity`, `qty_source`, `qty_inference_reason`, etc. (`csv_inventory_exporter.py`).
- **Divergence risk:** Low for **qty** if same primary product + consolidation list as API **when** export loads the same consolidated positions. **Semantic duplication high:** many columns repeat info also inside JSON if client used API JSON.
- **Naming:** `qty_source` (snake) vs API `qtySource` (camel) — same meaning.

### 4.6 Status model

| Concept | Meaning |
|---------|---------|
| **`Position.status`** | Lifecycle: `detected` → `reviewed` / `corrected` / `deleted` (`PositionStatus` enum). |
| **`needs_review`** | Operator queue flag; related to pipeline `count_status` at creation (`_needs_review_from_entity` in `v3_report_mapper`). |
| **`count_status`** | **Pipeline** counting outcome (e.g. `COUNTED`, `NEEDS_REVIEW`, …) — **not** the same as `Position.status`. |
| **`traceability_status`** | Validity of product/image traceability (e.g. valid/invalid) — orthogonal to position lifecycle. |
| **Aisle `status` + `error_code` / `error_message`** | Processing lifecycle vs last failure metadata (`AisleResponse`). |
| **`latest_job.status`** | Job machine state vs aisle aggregate status — related but different aggregates. |

**Finding:** Names like `status` appear everywhere; **document a glossary**. Not all are duplicates — some are **layered dimensions** (job vs aisle vs position vs count).

### 4.7 Product identity model

- **Canonical persisted identity:** `product_records.sku` (string, `UNKNOWN` sentinel when missing internal code at map time).
- **Pipeline canonical code:** `entity.internal_code` in `hybrid_report.json`.
- **Display fallbacks:** `_summary_sku_and_quantity_from_position` builds API `sku` from `internal_code` OR `review_display_label` OR `position_barcode` OR `pallet_id`.
- **CSV:** Exports `sku` (from summary mapping) **and** raw `internal_code` and `barcode` — operators can see conflicting strings if fallbacks differ from `product_records.sku`.

**Recommendation direction:** Public contract should expose **`product_id`** (record id) + **`canonical_sku`** (from product row) + optional **`display_label`** — fallbacks explicit, not overloaded into `sku`.

### 4.8 Quantity model

**Persisted (canonical row):**

- `product_records.detected_quantity` — resolved quantity at ingest (or after recompute rules).
- `product_records.corrected_quantity` — operator correction.
- `product_records.qty_source`, `qty_inference_reason`, `raw_qty_json`, `qty_parse_status` — provenance.

**Snapshot (JSON on position):**

- Pipeline inputs: `final_quantity`, `product_label_quantity`
- Resolver output: `qty_final`, `qty_source`, `qty_inference_reason`, `raw_qty`, `qty_parse_status`, `qty_origin_field`, `qty_is_resolved`

**Public API:**

- `qty` — “final” display quantity per v3.2.2 contract.
- `detected_quantity` — **often aligned to `qty`** when primary product exists (to avoid stale summary).
- `corrected_quantity` — surfaced when primary has correction.

**Proposed canonical mental model (see §5):**

1. **raw_observation** — label/pipeline fields + `raw_qty` + parse status  
2. **resolved_detected** — `detected_quantity` on product (post rules)  
3. **operator_final** — `corrected_quantity` if set, else resolved_detected  
4. **provenance** — `qty_source` + `qty_inference_reason` + optional raw payload reference  

---

## 5. Canonical source proposal

| Concept | Canonical SoT | Notes |
|---------|---------------|-------|
| **Inventory activity / freshness** | **Computed** `last_activity_at` for list; **DB** timestamps on `inventories`, `aisles`, `positions` for entity-level. | Avoid duplicating “last event” in multiple ad-hoc queries without a single helper. |
| **Aisle status vs latest job** | **Aisle** row status for business state; **job** summary for last run diagnostics. | Keep both but name in UI/docs (not one overwriting the other silently). |
| **Product identity (public)** | **`product_records.sku`** + stable **`product_records.id`** | Summary fallbacks only for **display**, not silent overwrite of `sku` column semantics. |
| **Final quantity (public)** | **`corrected_quantity` if not null else `detected_quantity`** on primary `ProductRecord`, except **documented** aggregated-SKU path where summary total is intentional override | Today implemented via `position_to_summary` + export CSV rule. |
| **Traceability** | **`traceability_status` + `source_image_id`** on entity, persisted into summary; enrichment from **`hybrid_report.json`** only when summary incomplete | Cache in `shared.py` is performance-only. |
| **Evidence linkage** | **`positions.primary_evidence_id`** + detail `evidences[]` | `has_evidence` is derived; `source_image_id` is **not** evidence id. |
| **Review state** | **`Position.status`** + **`review_actions`** history | `needs_review` is queue flag, not full state machine. |

---

## 6. Recommended contract cleanup

**Fields to keep (short term)**

- `id`, timestamps, `status`, `needs_review`, `confidence`, `qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved`, `has_evidence`, `traceability_status`, `source_image_id`, `primary_evidence_id`, `corrected_quantity` (when non-null).

**Fields to deprecate / narrow**

- `detected_summary_json` on **public** list: move to **detail-only** or `?include=technical` flag.
- `detected_quantity` on summary: **deprecate** in favor of documented meaning (“legacy alias for qty”) or remove in v4.

**Fields to rename (versioned API)**

- Unify **camelCase vs snake_case** between JSON API and CSV (pick one public style per channel or generate CSV from same DTO serializer).

**Move to debug / internal**

- `_audit`, `qty_origin_field`, duplicate `qty_*` inside summary if still needed for replay.

**Backward compatibility**

- Add **`X-Deprecated-Fields`** / OpenAPI `deprecated: true` on Pydantic fields before removal.
- Frontend: `PositionSummary` already flags `detected_summary_json` as backward compat — plan removal in sync with backend flag.

---

## 7. Persistence cleanup recommendations

- **Stop dual-writing** quantity resolution into `detected_summary_json` for fields already on `product_records` **once** all readers use `ProductRecord` (analytics today still hit `JSON_VALUE` on summary — see `sql_analytics_repository.py`).
- **Keep** `detected_summary_json` as **immutable pipeline snapshot** for audit/replay OR shrink to entity_uid + pipeline-only fields + reference to product id.
- **`corrected_summary_json`:** audit usage; if unused in practice, document or remove in migration.
- **Consolidation:** mutates representative’s `detected_summary_json` in memory (`position_sku_consolidation.py`); ensure **reconciliation job** or **clear rule** for `product_records` vs consolidated totals.

---

## 8. CSV cleanup recommendations

**Keep**

- Inventory / aisle identifiers, `position_id`, `position_code`, **`final_quantity`**, **`qty_source`**, **`qty_inference_reason`**, `position_status`, traceability, evidence/image ids, `needs_review`, `updated_at`.

**Remove or demote to “technical export”**

- **`internal_code` + `barcode` if `sku` becomes canonical** from one derivation; or keep **one** of duplicate code columns.
- **`detected_quantity` separate from `final_quantity`** — merge into documented columns only if operators need both; else drop.

**Rename**

- Align with API: either export `qtySource` (if CSV targets devs) or document that CSV is **snake_case view** of same contract.

**Align with API**

- Single function already delegates to `position_to_summary` — **preserve**; add automated test comparing a sample row to **serialized** `PositionSummary` JSON.

---

## 9. Suggested implementation plan

| Phase | Goal |
|-------|------|
| **1** | Publish internal glossary doc (status vs count_status vs job status; evidence vs source_image_id; sku vs internal_code). |
| **2** | Mark redundant API fields deprecated; telemetry on who still reads `detected_summary_json` keys. |
| **3** | Detail endpoint: optional `technical_snapshot` object instead of flat blob mixing concerns. |
| **4** | CSV: drop redundant columns; add regression test vs API DTO. |
| **5** | DB migration: slim `detected_summary_json`; migrate analytics to `product_records` where possible. |
| **6** | Frontend: use canonical fields only in new screens; keep shim for legacy. |

---

## 10. Open questions / risks

- **Aggregated SKU rows:** `ProductRecord` may not match consolidated `final_quantity` in summary — need **explicit** business rule: either update/delete child products on consolidate, or document that list/export uses **virtual** quantities.
- **Analytics SQL** depends on `detected_summary_json` — persistence cleanup **blocked** until queries rewritten.
- **Hybrid report enrichment** cache: if report and DB diverge, enrichment could theoretically disagree with stored summary (rare if immutable).
- **Multi-product positions:** “Primary product” selection rule hides ambiguity — duplicates may exist as **business** issue beyond JSON duplication.

---

## Appendix A — Key code references

| Concern | Location |
|---------|----------|
| API position shape | `backend/src/api/schemas/position_schemas.py` |
| Summary mapping | `backend/src/api/routes/v3/shared.py` — `position_to_summary`, `_summary_sku_and_quantity_from_position`, `_qty_contract_from_product`, `_resolve_qty_contract_from_position_legacy` |
| Pipeline snapshot | `backend/src/infrastructure/pipeline/v3_report_mapper.py` |
| Consolidation mutating summary | `backend/src/application/services/position_sku_consolidation.py` |
| CSV parity | `backend/src/application/mappers/inventory_export_rows.py`, `export_inventory_results.py` |
| SQL schema | `backend/src/database/schema.sql` (positions, product_records) |
| Frontend types | `frontend/src/api/types/responses.ts` |

---

*End of audit.*
