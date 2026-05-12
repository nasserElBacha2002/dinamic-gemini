# H4 — Additive audit persistence

## 1. Executive summary

**Final status:** `READY_FOR_H5_WITH_GAPS`

Successful v3 hybrid runs now persist a compact, safe **`run_audit_snapshot`** (schema `h4.v1`) inside **`job.result_json`**, built at pipeline success from in-memory run metadata (no artifact reads). **`RunAuditabilityService`** prefers this snapshot for execution-time audit fields when present; legacy jobs without a snapshot continue to aggregate from execution log, hybrid report, `visual_reference_context`, and joins. No SQL migration was introduced.

**Gaps (expected):** no metrics endpoints; no snapshot backfill for old jobs; `inventory_visual_references_used` remains null in the snapshot unless a reliable signal is added later.

---

## 2. What was implemented

| Area | Files | Responsibility |
|------|-------|----------------|
| Constant | `backend/src/pipeline/run_metadata.py` | `RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT = "run_audit_snapshot"` |
| Builder | `backend/src/application/services/run_audit_snapshot.py` | Pure `build_run_audit_snapshot(...)`; schema `h4.v1`; allowlisted fields only |
| Pipeline | `backend/src/pipeline/hybrid_inventory_pipeline.py` | Attach snapshot to `run_metadata` in `_build_success_run_metadata` |
| Persistence | `backend/src/infrastructure/pipeline/v3_job_execution_state.py` | `mark_success` copies snapshot dict into `job.result_json` |
| Read model | `backend/src/application/services/run_auditability_service.py` | Parse H4 snapshot; merge precedence snapshot → execution log → hybrid → VRC; `metadata_sources.run_audit_snapshot` |
| Models | `backend/src/application/services/run_auditability_models.py` | `RunAuditMetadataSources.run_audit_snapshot`; `to_jsonable` |
| Frontend types / panel | `frontend/src/api/types/responses.ts`, `frontend/src/components/JobAuditabilityPanel.tsx`, `frontend/src/i18n/locales/es/translation.json` | Typed `run_audit_snapshot` source + Spanish label for existing sources UI |
| Tests | `backend/tests/application/services/test_run_audit_snapshot.py`, updates to auditability / models / v3 state / API tests; frontend test fixtures | Builder, persistence, service merge, schema guard, API field |

---

## 3. Snapshot contract

**Key:** `run_audit_snapshot` (constant `RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT`).

**Schema version:** `h4.v1` — only dicts with this `schema_version` are treated as authoritative H4 snapshots by the read model.

| Field | Meaning | Source | Nullable? | Safe to expose? |
|-------|---------|--------|-------------|-----------------|
| `schema_version` | Snapshot format | Fixed `h4.v1` | No | Yes |
| `client_id` | Client at resolution time | SPR / caller | Yes | Yes (ID) |
| `inventory_id` | Inventory for run | Run context / SPR | Yes | Yes |
| `aisle_id` | Aisle for run | Run context / SPR | Yes | Yes |
| `client_supplier_id` | Supplier link | SPR / caller | Yes | Yes |
| `provider_name` | Analysis provider | Analysis result | Yes | Yes |
| `model_name` | Effective model | Composition / job model | Yes | Yes |
| `prompt_key` | Job prompt profile key | `run_metadata` | Yes | Yes |
| `prompt_version` | Legacy report tag | `run_metadata` | Yes | Yes |
| `supplier_prompt_config_id` | Resolved config row | `effective_prompt` / SPR | Yes | Yes |
| `supplier_prompt_config_version` | Config version | `effective_prompt` / SPR | Yes | Yes |
| `supplier_prompt_fallback_used` | Fallback flag | `effective_prompt` / SPR | Yes | Yes |
| `supplier_prompt_fallback_reason` | Stable reason code | `effective_prompt` / SPR | Yes | Yes |
| `protected_prompt_contract_key` | Contract key | `effective_prompt` | Yes | Yes |
| `protected_prompt_contract_version` | Contract version | `effective_prompt` | Yes | Yes |
| `effective_prompt_hash` | Hash of effective prompt | `effective_prompt` | Yes | Yes |
| `prompt_composition_available` | Composition present | In-memory composition | No | Yes |
| `reference_source` | Reference channel label | `effective_prompt` / VRC | Yes | Yes |
| `reference_image_count` | Count | Derived / VRC | Yes | Yes |
| `reference_ids` | Reference IDs | `effective_prompt` / VRC | No (may be `[]`) | Yes |
| `supplier_reference_images_used` | Supplier refs used | Derived from source/count | Yes | Yes |
| `inventory_visual_references_used` | Legacy inventory visual | Not set in H4 | Yes | Yes (null) |
| `warnings` | Observability warnings | Composition / SPR | No (may be `[]`) | Yes (short strings) |
| `metadata_sources` | What inputs existed at build | Builder flags | No | Yes |
| `created_at` | Snapshot creation (UTC ISO) | Wall clock at build | No | Yes |

**Safety rules:** never persist full prompt text, full `prompt_composition` blob, protected prompt body, or LLM request JSON. The builder only uses `merge_effective_prompt_fields` allowlists plus structural IDs/counts/booleans.

---

## 4. Persistence strategy

1. **`_build_success_run_metadata`** (hybrid pipeline) builds `run_metadata` (including `prompt_composition` and `visual_reference_context`), then calls **`build_run_audit_snapshot`** and sets **`run_metadata["run_audit_snapshot"]`**.
2. **`V3JobExecutionStateService.mark_success`** copies **`run_audit_snapshot`** from `run_metadata` into **`job.result_json`** alongside existing keys (`report_path`, `visual_reference_context`, `provider`, `prompt_key` / `prompt_version`, `llm_cost_snapshot`, durable artifacts merge).

Existing `result_json` fields are unchanged in shape; the new key is additive.

---

## 5. Read model integration

- **`RunAuditabilityService`** loads **`run_audit_snapshot`** when `schema_version == h4.v1` and sets **`metadata_sources.run_audit_snapshot = True`**.
- **Merge precedence** for audit fields (hash, supplier config, fallback, warnings, reference hints, provider/model/prompt attribution): **snapshot → execution log `effective_prompt` → hybrid `supplier_traceability` → `visual_reference_context`**.
- **Job row / aisle / inventory joins** remain authoritative for **current** relational identity (`client_id`, `client_supplier_id`, `inventory_id`, `aisle_id` from joins); the snapshot is **not** used to override those join-derived values in the view.

---

## 6. Backward compatibility

- Jobs without `run_audit_snapshot` behave as before (H1/H2 aggregation).
- Wrong or unknown `schema_version` is ignored (no `run_audit_snapshot` source flag).
- H2 GET auditability path unchanged; response gains optional **`metadata_sources.run_audit_snapshot`** (boolean).

---

## 7. Safety review

- No full prompt text, protected prompt body, or LLM request body is written to `result_json` via this snapshot.
- `SupplierPromptResolution.editable_instructions` is **not** copied into the snapshot.
- Snapshot does not embed the full `prompt_composition` object in `result_json`.

---

## 8. Tests and validation

| Command | Result |
|---------|--------|
| `cd backend && python3 -m pytest tests/application/services/test_run_auditability_service.py tests/application/services/test_run_auditability_models.py tests/application/services/test_run_auditability_execution_log.py tests/application/services/test_reference_usage_from_job_result.py tests/application/services/test_run_audit_snapshot.py tests/infrastructure/pipeline/test_v3_job_execution_state.py -q` | **27 passed** (with project coverage plugin) |
| `cd backend && python3 -m pytest tests/application/api/test_job_auditability_endpoint.py -q` | **1 skipped** on Python 3.9 (module requires 3.10+ per existing skip); run on 3.10+ for HTTP regression |
| `cd backend && python3 -m ruff check src/application/services/run_auditability_service.py` (and `--fix` where needed) | **All checks passed** |
| `cd frontend && npm test -- --run tests/JobAuditabilityPanel.test.tsx tests/useJobAuditability.test.tsx` | **6 passed** |

---

## 9. Remaining gaps

- No metrics endpoint (H5 scope).
- No SQL rollup columns.
- No frontend metrics dashboard.
- Old succeeded jobs have no snapshot unless backfilled.
- `inventory_visual_references_used` remains null in the snapshot unless a reliable pipeline signal is added.

---

## 10. Final recommendation for H5

Recommend **metrics backend with limited artifact fallback**: use **`run_audit_snapshot`** as the primary fact table for new jobs (client, supplier, provider/model, fallback, hash presence), and retain execution log / hybrid only for legacy rows or anomaly drills. Optional follow-up: **snapshot backfill** for high-value historical windows if analytics require pre-H4 cohorts.
