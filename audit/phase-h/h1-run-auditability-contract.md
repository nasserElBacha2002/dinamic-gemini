# H1 — Run auditability contract

## 1. Executive summary

**Final status:** `READY_FOR_H2_WITH_GAPS`

H1 delivers a **read-only aggregated view** (`RunAuditabilityView`) built by `RunAuditabilityService` from the job row, aisle/inventory joins, `result_json`, optional `hybrid_report.json`, and optional `execution_log.jsonl` (best-effort load). No migrations, no `mark_success` changes, and no pipeline or hybrid-report writer changes.

**Gaps for H2:** a public HTTP route is not wired yet; `inventory_visual_references_used` remains always `null` (v3 contracts do not expose legacy inventory visual reference usage as a boolean). Metrics that require a single SQL row of audit fields still need optional additive persistence (documented as H1.x / later).

---

## 2. What was implemented

| Path | Responsibility |
|------|----------------|
| `src/application/services/run_auditability_models.py` | `RunAuditabilityView`, `RunAuditMetadataSources`, `RunAuditReferenceUsage`, `to_jsonable()` |
| `src/application/services/run_auditability_execution_log.py` | Parse last `AnalysisStage` / `Analysis request prepared` / `event_type=analysis_request`; extract `effective_prompt` allowlist |
| `src/application/services/run_auditability_service.py` | `RunAuditabilityService.build(job_id)` — aggregation, `missing_metadata`, `legacy_mode`; depends on `RunAuditExecutionLogLoader` port |
| `src/application/ports/run_audit_execution_log_loader.py` | `RunAuditExecutionLogLoader` protocol (keeps application free of infra imports) |
| `src/infrastructure/artifacts/run_audit_execution_log_loader.py` | `DefaultRunAuditExecutionLogLoader` delegating to `try_read_execution_log_events_for_job` |
| `src/infrastructure/artifacts/stored_artifact_reader.py` | Moved `read_execution_log_events_for_job` from API module; added `try_read_execution_log_events_for_job` |
| `src/api/services/v3_stored_artifact_access.py` | Removed duplicate `read_execution_log_events_for_job` implementation (now only in `stored_artifact_reader`) |
| `src/api/routes/v3/aisles.py` | Import `read_execution_log_events_for_job` from `stored_artifact_reader` |
| `tests/application/services/test_run_auditability_service.py` | Happy path, missing hybrid, missing execution log, legacy, failed job, unknown job |
| `tests/application/services/test_run_auditability_execution_log.py` | Parser unit tests |
| `tests/api/test_v3_stored_artifact_access_unit.py` | Import execution log reader from infra |

---

## 3. RunAuditabilityView contract

| Field | Meaning | Source | Nullable? | Notes |
|-------|---------|--------|-----------|-------|
| `job_id` | Job primary key | Job row | No | |
| `status` | Job status enum value | Job row | No | String `.value` |
| `target_type` / `target_id` | Work target (e.g. aisle) | Job row | No | |
| `created_at` / `started_at` / `finished_at` | Lifecycle timestamps | Job row | started/finished nullable | |
| `inventory_id` | Owning inventory when target is aisle | Aisle join | Yes | |
| `aisle_id` | Aisle id when `target_type == aisle` | Derived from `target_id` | Yes | |
| `client_id` | Inventory client | Inventory join | Yes | |
| `client_supplier_id` | Aisle supplier link | Aisle or hybrid `supplier_references` | Yes | Hybrid can backfill when aisle missing field |
| `provider_name` | Pipeline / result provider | Job row, `result_json.provider` | Yes | |
| `model_name` | Model id | Job row | Yes | |
| `prompt_key` / `prompt_version` | Legacy profile tags | Job row, `result_json` | Yes | |
| `supplier_prompt_config_id` / `supplier_prompt_config_version` | Resolved supplier prompt config | Execution log `effective_prompt`, then hybrid `supplier_traceability.supplier_prompt` | Yes | Exec log preferred when present |
| `supplier_prompt_fallback_used` / `supplier_prompt_fallback_reason` | Supplier prompt resolver fallback | Same as above | Yes | |
| `protected_prompt_contract_key` / `protected_prompt_contract_version` | Protected contract identity | Execution log `effective_prompt` | Yes | Not duplicated in `supplier_traceability` today |
| `effective_prompt_hash` | Hash of effective prompt | Execution log `effective_prompt` | Yes | Absent when log missing |
| `prompt_composition_available` | Summary composition present on analysis_request | Execution log | No | Boolean |
| `reference_usage` | Parsed `visual_reference_context` | `result_json` via existing parser | Yes | |
| `supplier_reference_images_used` | Inferred from `reference_source` + counts | `result_json` / effective_prompt / hybrid | Yes | Tri-state when unknown |
| `inventory_visual_references_used` | Legacy inventory visual refs | — | **Always null in H1** | Cannot infer from current v3 artifacts |
| `reference_source` | e.g. `supplier_reference_images` | `result_json`, hybrid, effective_prompt | Yes | |
| `reference_image_count` | Count hint | Hybrid `image_count`, `result_json` | Yes | |
| `reference_ids` | Resolved reference id strings | `result_json` / effective_prompt ids | No | Empty list allowed |
| `warnings` | Composition warnings | Execution log `effective_prompt.warnings` | No | Empty list |
| `metadata_sources` | Which sources contributed | Service | No | Flags, not provenance per-field |
| `missing_metadata` | Keys still unknown after merge | Service heuristic | No | List may be non-empty for partial jobs |
| `legacy_mode` | Heuristic: no client and no supplier on joins | Derived | No | True when both ids blank after resolution |

---

## 4. Metadata source strategy

1. **Job row:** identity, status, timestamps, indexed `provider_name`, `model_name`, `prompt_key`, `prompt_version`.
2. **Aisle join:** when `target_type == aisle`, load aisle for `inventory_id`, `client_supplier_id`.
3. **Inventory join:** load `client_id`.
4. **`result_json`:** `provider`, `visual_reference_context` (existing parser), optional durable pointers (not expanded in H1).
5. **`hybrid_report`:** `StoredArtifactReader.load_hybrid_report_json_for_job` (existing best-effort behavior).
6. **`execution_log`:** injected :class:`~src.application.ports.run_audit_execution_log_loader.RunAuditExecutionLogLoader` (production: :class:`~src.infrastructure.artifacts.run_audit_execution_log_loader.DefaultRunAuditExecutionLogLoader` → `try_read_execution_log_events_for_job`), then last matching `analysis_request` event.

Merge precedence for supplier / effective fields: **execution log `effective_prompt` first**, then hybrid `supplier_traceability` for ids/fallback/reference summary.

---

## 5. Legacy and missing metadata behavior

- Missing job → `build` returns `None`.
- Unexpected exception during aggregation → logged and **minimal** `RunAuditabilityView` with `missing_metadata` containing `auditability_aggregate_error` and `legacy_mode=True` (defensive).
- Missing hybrid and/or execution log → corresponding `metadata_sources` flags false; `missing_metadata` lists `hybrid_report` / `execution_log`; dependent fields stay null unless supplied elsewhere.
- **Legacy heuristic:** `legacy_mode` when no `client_id` and no `client_supplier_id` after joins and hybrid backfill.

---

## 6. H0 gaps addressed

| H0 gap | H1 response |
|--------|-------------|
| `prompt_composition` not on `result_json` | Read model reads execution log + hybrid instead; does not require DB change |
| Fragmented audit trail | Single `RunAuditabilityView` + `to_jsonable()` for H2 |
| Client/supplier not on job row | Explicit joins in service |
| Execution log load raised from API | `try_read_execution_log_events_for_job` for safe aggregation; strict reader moved to infra for reuse |

**Still open (by design in H1):** no HTTP route; no persistence of composition on the job row.

---

## 7. Remaining gaps for H2 / H3 / H4

- **HTTP:** `GET /api/v3/jobs/{job_id}/auditability` (or inventory-scoped variant) should call `RunAuditabilityService` and return `RunAuditabilityView.to_jsonable()`.
- **Frontend:** types + optional panel in observability workspace.
- **Additive persistence (optional H4):** persist a compact audit snapshot or `prompt_composition` summary on the job row for SQL metrics and offline support without artifact fetches.
- **`inventory_visual_references_used`:** needs explicit product rule + data source if still relevant post–Phase G legacy cleanup.

---

## 8. Tests and validation

Commands:

```bash
cd backend
python3 -m pytest tests/application/services/test_run_auditability_service.py tests/application/services/test_run_auditability_execution_log.py -q
python3 -m ruff check src/application/services/run_auditability_*.py src/application/ports/run_audit_execution_log_loader.py src/infrastructure/artifacts/run_audit_execution_log_loader.py src/infrastructure/artifacts/stored_artifact_reader.py src/api/routes/v3/aisles.py src/api/services/v3_stored_artifact_access.py
# Result: 8 passed; ruff clean on listed paths (local run).
```

**Note:** Full `pytest` / `tests/api/test_v3_stored_artifact_access_unit.py` may require a Python version compatible with the repo’s typing syntax in `src/auth/config.py` (environment-specific).

---

## 9. Final recommendation

**H2 should be pure API endpoint work** (plus OpenAPI/schema export if used): wire `RunAuditabilityService` in dependencies, authorize like other inventory-scoped job reads, return `to_jsonable()`. **Additive persistence is not a blocker** for H2 given H1 read paths; add persistence only if product requires artifact-free metrics or simpler support tooling.
