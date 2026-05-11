# G5.1 — Deprecation hardening

## 1. Executive summary

**Status: `G5_1_READY_FOR_G5_2`**

No additional application code changes were required in this pass: Phase **C8/C9** already disabled legacy writes and removed inventory-scoped reference routes, repositories, and UI. The API regression suite asserts **404** on all legacy visual-reference paths. Active uploads are **supplier_reference_images** only.

## 2. Scope implemented

- Re-verified absence of legacy create/list/upload/delete routes and use cases under `backend/src` (Python).
- Re-verified absence of legacy client calls under `frontend/src`.
- Confirmed guard test `tests/api/test_inventory_visual_references_removed.py` remains in place.

## 3. Backend changes

**None** (no new commits in this subphase). Existing behavior:

- Legacy paths → **404** (routes unregistered).
- Pipeline references → **`supplier_reference_images`** only.

## 4. Frontend changes

**None.** Supplier reference management remains on client/supplier surfaces.

## 5. Tests updated

**None** in this subphase. Existing tests continue to enforce removal.

## 6. Legacy read-only compatibility retained

- Historical job metadata and execution-log parsing unchanged.
- `VisualReferenceContext` / attachment summaries remain for observability.

## 7. Validation results

See **`audit/raw/phase-g/g5-1-validation.txt`**.

## 8. Risks / observations

External integrations that still POST to removed URLs will receive **404** — correct deprecation signal; document in release notes if needed.

## 9. Recommendation for G5.2

Confirm row counts and migration policy on the **real** database (`g5-0-db-checks.sql`). Use existing **`backend/scripts/analyze_legacy_reference_migration.py`** when legacy rows might exist before applying **`0029`**.
