# G5.0 — Legacy reference read-only audit

## 1. Executive summary

**Status: `G5_0_READY_WITH_OBSERVATIONS`**

The active Python and TypeScript application trees contain **no** references to `inventory_visual_references` or legacy inventory visual-reference APIs. Operational reference resolution is exclusively via **`supplier_reference_images`** (`SupplierReferenceImageResolver`, `AisleAnalysisContextBuilder`). Historical migrations still mention the legacy table; guarded migration **`0029_drop_inventory_visual_references.sql`** drops the table only when empty. **`schema.sql`** does not define `inventory_visual_references`.

**Observation:** SQL Server was not reachable from the audit workspace (login timeout), so live row counts and migration apply state were **not** verified here. Operators must run **`audit/raw/phase-g/g5-0-db-checks.sql`** on the target database.

## 2. Method

- Repository-wide `rg` for `inventory_visual_references` and legacy identifiers; outputs saved under `audit/raw/phase-g/`.
- Scoped review of `backend/src` (excluding migrations): Python grep for `inventory_visual` → **zero** matches in `*.py`.
- Review of `frontend/src` for legacy routes/API calls → **zero** matches.
- Read `0029_drop_inventory_visual_references.sql`, `docs/reference-images.md`, `tests/api/test_inventory_visual_references_removed.py`.
- Attempted `python3 scripts/db_migrate.py status` → failed (see `audit/raw/phase-g/g5-0-db-results.txt`).

## 3. Static references found

| Area | Finding |
| --- | --- |
| `backend/src/database/migrations/versions/*.sql` | Historical CREATE/ALTER (`0002`–`0005`); **`0029`** conditional DROP |
| `backend/scripts/` | `analyze_legacy_reference_migration.py`, `legacy_reference_migration_classifier.py` — operator/migration tooling, not runtime API |
| `audit/`, `docs/` | Phase C9/C10/G0 documentation |
| `backend/tests/` | Removal guard `test_inventory_visual_references_removed.py`; migration test for 0029 |

Primary grep artifacts:

- `audit/raw/phase-g/g5-0-reference-grep.txt` — `backend/src`, `frontend/src`, tests (first pass)
- `audit/raw/phase-g/g5-0-reference-grep-full.txt` — full-repo `inventory_visual_references` (truncated sample)

## 4. Active API usage

**None.** Legacy routes under `/api/v3/inventories/{id}/visual-references` return **404** (verified by `test_inventory_visual_references_removed.py`). No `inventory_visual_reference` symbols in `backend/src/**/*.py`.

## 5. Active frontend usage

**None** in `frontend/src` (no `inventory_visual`, `visual-references`, or legacy upload helpers). Supplier reference UX remains under client/supplier routes.

## 6. Active pipeline usage

**No read path from `inventory_visual_references`.** The aisle pipeline builds `AnalysisContext.visual_references` from **`supplier_reference_images`** via `SupplierReferenceImageResolver` / `AisleAnalysisContextBuilder`. `VisualReferenceContext` and paths like `inventories/.../visual_references/...` in tests denote **in-memory or historical JSON paths**, not live queries to the dropped table.

## 7. Database / table status

- **Canonical `schema.sql`:** does **not** include `inventory_visual_references` (aligned with post-C9 mirror).
- **Migration `0029`:** drops table **only if** it exists **and** has **zero** rows; otherwise throws `51029`.
- **Live DB:** not verified in this environment — use **`g5-0-db-checks.sql`**.

## 8. Historical observability considerations

Preserved by design:

- **Job `result_json`** / execution logs may still mention `reference_usage`, `visual_reference_context`, `visual_reference_attachments` — read-only parsing (`reference_usage_from_job_result.py`, frontend execution log parsing).
- **Hybrid pipeline** metadata and tests use `visual_references` on `AnalysisContext` as a **contract**, not as a DB table name.

## 9. Risks and blockers

| Risk | Mitigation |
| --- | --- |
| Production DB still has rows in `inventory_visual_references` | Do **not** apply `0029` until migrated/archived; run `analyze_legacy_reference_migration.py` / operator playbook |
| Env assumes table exists | Older DBs: migrations create table; `0029` safe only when empty |

## 10. Recommendation for G5.1

Proceed to **G5.1** as **verification-only**: active creation paths are already absent (Phase C8/C9). Document any operator-only hardening if external clients still call removed URLs.
