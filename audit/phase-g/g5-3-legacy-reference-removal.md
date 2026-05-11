# G5.3 — Legacy reference removal / finalization

## 1. Executive summary

**Status: `G5_3_READY_FOR_REVIEW`**

The repository already contains **migration `0029_drop_inventory_visual_references.sql`** with a **non-empty guard** (`THROW 51029`). No duplicate DROP migration was added. **`schema.sql`** does not recreate `inventory_visual_references`. Active Python and frontend source contain **no** legacy repository or route code.

**Database layer:** Actual DROP occurs only when migration **0029** runs successfully against an environment where the table is empty (or absent — script no-ops).

## 2. Preconditions verified

| Precondition | Evidence |
| --- | --- |
| Active app does not depend on table | `rg` over `backend/src/**/*.py` → no matches |
| Active frontend does not call legacy API | `frontend/src` grep → no matches |
| Guarded migration exists | `0029_drop_inventory_visual_references.sql` |
| Removal tests | `test_inventory_visual_references_removed.py`, `test_migration_0029_drop_inventory_visual_references.py` |

## 3. Migration decision

- **Do not add** a new `00XX_drop_inventory_visual_references_if_empty.sql` — **`0029`** fulfills the requirement.
- Historical migrations (`0002`–`0005`) intentionally retain DDL history; **0029** finalizes removal when applied.

## 4. Schema mirror updates

**Already aligned:** `backend/src/database/schema.sql` contains **no** `inventory_visual_references` table definition (post-C9 snapshot).

## 5. Code removal / deprecation changes

**None required in this G5 pass** — removal was completed in Phase C9 per audit trail.

## 6. Validation results

See **`audit/raw/phase-g/g5-3-validation.txt`**.

## 7. Rollback considerations

- If **`0029`** was applied and the table must be restored: restore from backup or re-run historical migrations on a fresh DB — **not** a forward downgrade path in-repo.
- Forward migrations after **0029** assume the legacy table is gone.

## 8. Recommendation for G5.4

Run full validation bundle (pytest, frontend build, operator SQL checklist). Close G5 after documenting DB connectivity limits.
