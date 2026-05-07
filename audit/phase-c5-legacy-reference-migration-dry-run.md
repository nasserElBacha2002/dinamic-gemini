# C5 — Legacy Reference Migration Dry-Run

## 1. Executive summary

**Status:** **READY_WITH_OBSERVATIONS**

- **Deliverables complete:** read-only classifier, SQL SELECT analyzer script, unit tests, CSV/JSON templates, and migration recommendations for C6.
- **Observation:** Real production counts are **environment-dependent**. In this pass the analyzer could not complete SQL (`HYT00` login timeout against SQL Server), so `phase-c5-legacy-reference-migration-summary.json` currently reflects **`db_connected: false`** and **zero rows**. Re-run locally or in CI with valid `SQLSERVER_*` / `SQLSERVER_CONNECTION_STRING` and network access to populate counts.
- **Not blocked:** Classification rules and tooling are implemented; product still must sign off ambiguous-inventory policies before C6 execution.

---

## 2. Scope

| In scope (C5) | Out of scope |
|---------------|--------------|
| Quantification **design**, SELECT-only queries, per-row **classification** logic | INSERT/UPDATE/DELETE/MERGE/DDL |
| Heuristic `SKIP_ALREADY_MIGRATED` (no mapping table yet) | Physical file copy/move |
| Reports: JSON summary, CSV detail, SQL log, open decisions | Pipeline switch, API/UI changes |
| Unit tests for pure classifier | Real migration (C6) |

---

## 3. Data summary

Values below mirror **`audit/raw/phase-c5-legacy-reference-migration-summary.json`** at report time.

| Metric | Value (stub run) |
|--------|------------------|
| `total_legacy_reference_rows` | 0 |
| `distinct_inventories_with_legacy_references` | 0 |
| `inventories_with_client_id` | 0 |
| `inventories_without_client_id` | 0 |
| `inventories_with_zero_supplier_assignments` | 0 |
| `inventories_with_one_supplier_assignment` | 0 |
| `inventories_with_multiple_supplier_assignments` | 0 |
| `legacy_references_auto_single_supplier` | 0 |
| `legacy_references_auto_legacy_default_supplier` | 0 |
| `legacy_references_ambiguous_multi_supplier` | 0 |
| `legacy_references_ambiguous_missing_client` | 0 |
| `legacy_references_ambiguous_no_supplier` | 0 |
| `legacy_references_skip_already_migrated` | 0 |
| `legacy_references_skip_missing_storage` | 0 |
| `legacy_references_skip_invalid_row` | 0 |
| `auto_mappable_rows` | (AUTO_SINGLE + AUTO_LEGACY_DEFAULT) |
| `ambiguous_rows` | (MULTI + MISSING_CLIENT + NO_SUPPLIER) |
| `missing_storage_rows` | same as skip_missing_storage |

**Derived formulas (analyzer):**

- `auto_mappable_rows` = `legacy_references_auto_single_supplier` + `legacy_references_auto_legacy_default_supplier`
- `ambiguous_rows` = `legacy_references_ambiguous_multi_supplier` + `legacy_references_ambiguous_missing_client` + `legacy_references_ambiguous_no_supplier`

---

## 4. Classification results

Categories implemented in `backend/scripts/legacy_reference_migration_classifier.py`:

| Category | Meaning |
|----------|---------|
| `AUTO_SINGLE_SUPPLIER` | Inventory has `client_id`; exactly one distinct non-null `aisles.client_supplier_id`; supplier row’s `client_id` matches inventory. |
| `AUTO_LEGACY_DEFAULT_SUPPLIER` | Inventory has `client_id`; zero aisle suppliers; `Legacy Default Supplier` exists for that client; `--accept-default-supplier-fallback` (default on). |
| `AMBIGUOUS_MULTI_SUPPLIER` | More than one distinct aisle supplier under the inventory. |
| `AMBIGUOUS_MISSING_CLIENT` | `inventories.client_id` is null. |
| `AMBIGUOUS_NO_SUPPLIER` | Client present, no aisle suppliers, no acceptable legacy default (missing row or fallback disabled). |
| `SKIP_ALREADY_MIGRATED` | Heuristic match on `(client_supplier_id, storage_path)` or `(client_supplier_id, storage_key)` against existing `supplier_reference_images`. |
| `SKIP_MISSING_STORAGE` | Incomplete provider metadata or empty legacy path (see `storage_metadata_sufficient`). |
| `SKIP_INVALID_ROW` | Invalid MIME/size/filename, orphan inventory join, supplier/client mismatch, or corrupted legacy-default linkage. |

---

## 5. Ambiguous cases & storage risks

- **Examples:** When DB-connected, see `audit/raw/phase-c5-legacy-reference-migration-examples-extract.md` (up to `--limit-examples` per bucket).
- **Filtered CSVs** (populated when matching rows exist):  
  `phase-c5-missing-storage-candidates.csv`, `phase-c5-ambiguous-multi-supplier-inventories.csv`, `phase-c5-missing-client-inventories.csv`, `phase-c5-default-supplier-candidates.csv`.
- **Local file probe:** Optional `--check-local-files` resolves `output_dir/v3_uploads/{storage_path}` when `artifact_storage_legacy_local_read_enabled` is true and row is legacy path–only (provider absent).

---

## 6. Mapping recommendation for C6

Default proposal (matches C5 prompt; enforced in classifier + analyzer):

1. **Single supplier:** If inventory has `client_id` and aisles expose exactly one distinct `client_supplier_id` belonging to that client → migrate each legacy reference to that supplier (`AUTO_SINGLE_SUPPLIER`).
2. **No aisle supplier:** If inventory has `client_id`, no aisle suppliers, and `Legacy Default Supplier` exists for that client → migrate with product-approved fallback (`AUTO_LEGACY_DEFAULT_SUPPLIER`). Use `--no-accept-default-supplier-fallback` to stress-test `AMBIGUOUS_NO_SUPPLIER` counts.
3. **Multiple suppliers:** **No default auto-migrate** → `AMBIGUOUS_MULTI_SUPPLIER`; require duplication strategy, default-supplier consolidation, manual mapping, or primary-supplier rule **before** C6 batch.
4. **Missing client:** **No default auto-migrate** → `AMBIGUOUS_MISSING_CLIENT`; assign client or explicit legacy client policy first.
5. **Missing / inconsistent storage metadata:** `SKIP_MISSING_STORAGE` — fix rows or restore blobs before migration.
6. **Supplier/client mismatch** (data integrity): `SKIP_INVALID_ROW`.
7. **Already migrated:** Heuristic only until **`legacy_reference_image_migration_map`** exists (recommended).

---

## 7. Storage migration recommendation

| Option | Recommendation |
|--------|----------------|
| **A — Pointer reuse** | Faster, shares blob between legacy and supplier rows. **Risk:** deleting one side breaks the other; unclear ownership for audits. |
| **B — Physical copy** | Preferred for **final** removal of `inventory_visual_references` (C9): independent lifecycle per row; aligns with `client_suppliers/{id}/reference_images/...` layout. |

**C5 stance:** Prefer **Option B** for the definitive cutover once volume/cost is acceptable; optionally **A** only as a short-lived bridge with mapping-table enforcement.

---

## 8. Migration mapping table proposal

**Recommended:** **Yes — required for safe C6/C9.**

Proposed table: `legacy_reference_image_migration_map` (additive migration in C6), fields aligned with product audit:

- `legacy_reference_id`, `legacy_inventory_id`
- `target_client_id`, `target_client_supplier_id`, `supplier_reference_image_id`
- `migration_batch_id`, `migration_status`, `migration_strategy`
- `source_*` / `target_*` storage provider metadata + paths/keys
- `created_at`, nullable `error_message`

**Retention:** Keep for audit **through C10** (or per compliance retention); supports idempotent re-runs, rollback pointers, and explaining historical `visual_reference_context.reference_ids` vs new supplier IDs.

---

## 9. Idempotency and rollback requirements for C6

1. **Idempotent batches:** Upsert by `legacy_reference_id` in mapping table; skip completed rows.
2. **Transaction boundaries:** DB insert + storage write ordering with compensating deletes on partial failure (mirror `upload_inventory_visual_references` rollback discipline).
3. **Rollback:** Mapping table marks `failed` / `rolled_back`; restore legacy table untouched until explicit delete phase (C9).
4. **VERIFY:** Re-run this analyzer; `SKIP_ALREADY_MIGRATED` should trend toward mapping-driven certainty rather than path heuristic alone.

---

## 10. Generated artifacts

| Artifact | Role |
|----------|------|
| `audit/phase-c5-legacy-reference-migration-dry-run.md` | This report |
| `audit/raw/phase-c5-legacy-reference-migration-summary.json` | Machine-readable counts |
| `audit/raw/phase-c5-legacy-reference-migration-details.csv` | Per-reference classification |
| `audit/raw/phase-c5-legacy-reference-migration-sql-results.txt` | Last DB attempt log |
| `audit/raw/phase-c5-query-catalog.txt` | SELECT catalog (stable) |
| `audit/raw/phase-c5-legacy-reference-migration-open-decisions.md` | Product decision prompts |
| `audit/raw/phase-c5-legacy-reference-migration-examples-extract.md` | Sample ids per category |
| `backend/scripts/analyze_legacy_reference_migration.py` | Analyzer entrypoint |
| `backend/scripts/legacy_reference_migration_classifier.py` | Pure classification |
| `backend/tests/scripts/test_analyze_legacy_reference_migration.py` | Classifier tests |

Optional CSVs appear when non-empty: see §5.

---

## 11. Commands executed

```bash
cd backend
python3 -m pytest tests/scripts/test_analyze_legacy_reference_migration.py -q
python3 -m ruff check scripts/legacy_reference_migration_classifier.py scripts/analyze_legacy_reference_migration.py tests/scripts/test_analyze_legacy_reference_migration.py
python3 scripts/analyze_legacy_reference_migration.py --output-dir ../audit/raw --limit-examples 20 --no-check-local-files
```

**Note:** Full-suite `pytest --collect-only` / frontend checks were **not** required for C5 scope (data/backend analyzer focus).

---

## 12. Blockers / required product decisions

See **`audit/raw/phase-c5-legacy-reference-migration-open-decisions.md`**.

Minimum before C6 execution:

1. Policy for **multi-supplier inventories**.
2. Policy for **NULL `inventories.client_id`**.
3. Confirm **Legacy Default Supplier** fallback acceptance (vs forcing aisle linkage).
4. Retention / archival window for legacy blobs.

---

## 13. Recommended next phase

**C6 — Real migration/copy to `supplier_reference_images`** with mapping table, storage strategy (prefer physical copy), and staged verification runs.
