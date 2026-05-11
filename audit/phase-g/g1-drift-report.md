# G1 — Drift metrics and read-only validation

**Date:** 2026-05-11  
**Artifacts:** `backend/scripts/client_oriented_drift_report.py`, `audit/raw/phase-g/g1-drift-report.json`, `audit/raw/phase-g/g1-runbook.txt`

---

## 1. Executive summary

This G1 slice adds a **reproducible, SELECT-only** drift reporting script and baseline documentation. A full numeric drift snapshot **requires a successful ODBC connection** to a SQL Server database containing v3 tables.

**Latest automated run (this session):** the script executed but **did not connect** to SQL Server (`Login timeout expired` in the sandbox/CI-like environment). The JSON report therefore has **`db_connected: false`** and **empty metric sections**.

**Readiness for G2 (enforce `client_id` on *new* inventory writes only):**

```text
READY_FOR_G2_WITH_OBSERVATIONS
```

**Rationale:** With no live DB metrics, G2 product work may proceed **only** with explicit awareness that drift has not been measured in this environment. After a successful DB run, re-evaluate using the script’s `readiness_for_g2_enforce_new_inventory_client` field:

- `NOT_READY_FOR_G2` if `client_id_orphan_missing_client_row` > 0 (invalid FK-like references).
- `READY_FOR_G2_WITH_OBSERVATIONS` if recent-window NULL `client_id` inventories exist or historical NULLs remain.
- `READY_FOR_G2` if no orphan rows, no recent NULLs, and no historical NULLs.

---

## 2. Method

| Item | Detail |
|------|--------|
| Script | `backend/scripts/client_oriented_drift_report.py` |
| SQL safety | Statements must start with `SELECT` or `WITH`; rejected if `\b(INSERT\|UPDATE\|…)\b` appears |
| DB access (this session) | **Failed** — ODBC login timeout (no reachable SQL Server from sandbox) |
| Queries | **100% SELECT-only** when DB is reachable |
| Raw output | `audit/raw/phase-g/g1-drift-report.json` |
| Runbook | `audit/raw/phase-g/g1-runbook.txt` |
| Baseline SQL | `audit/raw/phase-g/g0-db-checks.sql` (G0 checklist; extended in Python for prompt/image/job sampling) |

**Operator action:** Re-run from `backend/` with valid `.env` (see runbook). Optionally `--require-db` in CI once a SQL test instance is wired.

---

## 3. Inventory client drift

Populate from `g1-drift-report.json` → `inventory_client_drift` after a successful run.

| Metric (script key) | Meaning |
|---------------------|---------|
| `total_inventories` | Row count `inventories` |
| `client_id_null` / `client_id_not_null` | Legacy vs associated |
| `client_id_orphan_missing_client_row` | `client_id` set but no `clients` row — **blocker** |
| `inventories_with_inactive_client` | `clients.status` ≠ `active` |
| `client_id_null_created_last_{N}_days` | Recent drift signal (`N` = `--recent-days`) |

**Interpretation:** Historical NULLs are expected until G4.1. **Orphan** references must be fixed before any NOT NULL migration.

---

## 4. Aisle supplier drift

| Metric (script key) | Meaning |
|---------------------|---------|
| `total_aisles` | All aisles |
| `client_supplier_id_null` / `_not_null` | Supplier assignment |
| `aisles_whose_inventory_has_null_client` | Expected legacy pattern |
| `aisles_supplier_set_but_inventory_no_client` | **Integrity anomaly** (should be rare; backend rejects on create) |
| `aisles_supplier_client_mismatch` | Supplier not under inventory’s client |
| `aisles_orphan_client_supplier_id` | FK drift |
| `aisles_with_inactive_supplier` | Supplier status |
| `client_supplier_id_null_created_last_{N}_days` | Recent drift |

---

## 5. Supplier reference image readiness

| Metric | Meaning |
|--------|---------|
| `total_client_suppliers` | Universe |
| `total_supplier_reference_images` | Rows in `supplier_reference_images` |
| `suppliers_with_at_least_one_image` / `_with_zero_images` | Coverage |
| `active_suppliers_with_zero_images` | G6 / operations signal |

---

## 6. Legacy inventory visual references status

Script checks `INFORMATION_SCHEMA.TABLES` for `inventory_visual_references`:

- If **exists:** reports `row_count`.
- If **absent:** documents likely prior migration **0029** drop in that environment.

---

## 7. Supplier prompt config readiness

| Metric | Meaning |
|--------|---------|
| `total_prompt_config_rows` | All versions |
| `distinct_suppliers_with_active_config` | At least one `is_active=1` |
| `suppliers_without_active_config` | Candidates for prompt fallback |
| `rows_by_provider_name_key` | Distribution (NULL/empty = all-providers scope) |
| `multiple_active_violation_count` | Should be **0** if unique filtered index is enforced |

---

## 8. Job metadata JSON path sampling

When DB is connected, the script:

1. Selects the **most recent** `inventory_jobs` rows (limit `--job-json-sample-limit`).
2. Parses `result_json` and `payload_json` where valid JSON.
3. Emits:
   - **`substring_hits_among_sample_rows`**: how many sampled jobs’ combined JSON text contains substrings such as `fallback_used`, `effective_prompt_hash`, `prompt_composition`, `client_supplier_id`, `supplier_reference_resolution`.
   - **`top_json_dot_paths_in_sample`**: flattened key paths (depth-limited) for discovery.
4. Runs a **coarse** `LIKE '%fallback_used%true%'` count on all `result_json` rows (`approx_jobs_result_json_fallback_used_true_like`) — may include false positives; treat as heuristic.

**`job_events`:** Legacy Stage-8 table references `jobs(id)`, not `inventory_jobs`. v3 timeline detail is primarily **`inventory_jobs` JSON** + file-based execution logs. See `job_events_note` in JSON.

---

## 9. Recent fallback usage

After DB connect:

- Use `substring_hits` and `approx_jobs_result_json_fallback_used_true_like` as first-pass signals.
- For accurate booleans, follow-up **G1.1** should add `JSON_VALUE` probes once canonical paths are confirmed from `top_json_dot_paths_in_sample`.

---

## 10. Static legacy exposure findings

Confirmed by G0 + code inspection (unchanged in G1):

| Area | Still allows legacy? |
|------|----------------------|
| Frontend inventory create | Yes — `dialogs.inventory.client_none_option` + omit `client_id` in POST body (`CreateInventoryDialog.tsx`) |
| Backend create inventory | Optional `client_id` (`CreateInventoryRequest`) |
| Aisle create | Optional `client_supplier_id`; supplier required in UI only when inventory has client (`CreateAisleDialog.tsx`) |
| Tests | Explicit legacy-null inventory test (`test_create_inventory_with_explicit_null_client_id_keeps_legacy_behavior`) |
| Scripts | `backfill_legacy_client_supplier_defaults.py`, legacy reference analyzers under `backend/scripts/` |

---

## 11. Risks and blockers for G2

- **Unknown drift** until DB report runs — risk of surprising operators when `client_id` becomes mandatory on create.
- **Orphan `client_id`** values — script flags; must remediate data before enforcement if non-zero.
- **Integrations** (non-UI) posting inventories without `client_id` — will break when G2 lands; inventory API consumers need notice.

---

## 12. Risks and blockers for G3

- Aisles on inventories **without** clients today legitimately omit supplier; G3 must define behavior **after** G2 (inventory must have client before supplier enforcement).
- **Mismatch / orphan** supplier IDs — script counts; fix data before hard enforcement.

---

## 13. Risks and blockers for G4 NOT NULL migrations

- Any **non-zero** `client_id_null` or `client_supplier_id_null` without a backfill plan blocks G4.1 / G4.2.
- Long-running `ALTER COLUMN ... NOT NULL` on large tables — plan maintenance window + rollback scripts per org process.

---

## 14. Recommended next slices

1. **G1 follow-up (optional G1.1):** Run script on staging; paste metrics into this doc; add `JSON_VALUE` queries for canonical paths.  
2. **G2** — Require `client_id` on new inventory API + UI.  
3. **G3** — Require `client_supplier_id` on new aisles when inventory has client.  
4. **G4.1 / G4.2** — NOT NULL + backfill.  
5. **G5** — Legacy visual reference table removal when empty.  
6. **G6** — Prompt fallback policy.  
7. **G7** — Phase G closure.

---

## 15. Final recommendation

```text
READY_FOR_G2_WITH_OBSERVATIONS
```

**Condition:** Re-run `client_oriented_drift_report.py` against staging/production-read replica before merging G2; if `readiness_for_g2_enforce_new_inventory_client` returns `NOT_READY_FOR_G2`, execute **G1.1 data remediation** first.
