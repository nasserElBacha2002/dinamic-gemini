# G5.2 — Legacy reference data migration / archive decision

## 1. Executive summary

**Status: `G5_2_READY_FOR_G5_3`** (with operator verification prerequisite)

Repository evidence (Phase C5/C6 audits and tooling) supports **`total_legacy_reference_rows: 0`** for at least one validated environment; **production must still be checked** before dropping the table.

## 2. Current data status

| Source | Status |
| --- | --- |
| This workspace SQL Server | **Not reachable** — see `audit/raw/phase-g/g5-0-db-results.txt` |
| Canonical tooling | `backend/scripts/analyze_legacy_reference_migration.py` — dry-run classifier for legacy rows |
| Prior phase audits | C6 documented NO_OP when zero rows |

**Operators:** run `audit/raw/phase-g/g5-0-db-checks.sql` for authoritative counts.

## 3. Selected policy

Hybrid:

- **Policy A** applies if `inventory_visual_references` is **absent** or **empty** → proceed with **`0029`** apply when migration chain reaches that version.
- **Policy B** if rows exist and map cleanly → plan controlled copy to **`supplier_reference_images`** using existing classifier/migration scripts; **explicit `--apply`** only after dry-run sign-off (do not duplicate script logic here — reuse repo tooling).
- **Policy C** if rows must remain for audit → **skip DROP**; table stays read-only; codebase already does not write.
- **Policy D** if unmappable → block DROP until manual remediation.

No new **`migrate_inventory_visual_references_to_supplier_images.py`** was added: the repository already contains **`analyze_legacy_reference_migration.py`** and **`legacy_reference_migration_classifier.py`** for dry-run classification.

## 4. Migration / archive plan

1. Run SELECT-only checks (`g5-0-db-checks.sql`).
2. If count > 0: run **`analyze_legacy_reference_migration.py`** (dry-run) per Phase C5 playbook; resolve conflicts before DELETE/DROP.
3. If count = 0: **`0029_drop_inventory_visual_references.sql`** is safe to apply when the migration runner reaches it.

## 5. Script behavior (existing)

- **`legacy_reference_migration_classifier.py`**: pure classification helpers.
- **`analyze_legacy_reference_migration.py`**: DB-oriented analyzer (dry-run by design; `--apply` patterns per script docs).

## 6. Dry-run results

Not executed against a live DB in this workspace (connection timeout). Placeholder output path if operators run locally: **`audit/raw/phase-g/g5-2-legacy-reference-migration.json`** — populate after production dry-run.

## 7. Apply results

Not applicable in this environment.

## 8. Remaining blockers

- **Production row count unknown** until operators run SQL checks.

## 9. Recommendation for G5.3

If counts are zero and governance approves: ensure migration **`0029`** is applied in order via **`db_migrate`**. Do not author a second DROP migration — **`0029`** already implements guarded drop.
