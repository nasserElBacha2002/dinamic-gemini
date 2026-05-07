# C10 — Phase C Final Closure

## 1. Executive summary

**Status: PHASE_C_CLOSED_WITH_OBSERVATIONS**

Phase C’s target architecture is in place: **supplier_reference_images** is the single canonical operational store; the active aisle pipeline resolves reference attachments from **supplier rows** keyed by **`aisles.client_supplier_id`**; legacy inventory visual-reference **API/UI/backend modules** are removed; historical **`reference_usage`** / **`visual_reference_context`** / execution-log fields remain for job observability.

**Observation:** `scripts/db_migrate.py status|validate` could not be executed in the closure environment (SQL Server connection timeout). Static migration/schema checks and automated tests passed; operators should confirm migration **0029** applied and DB status in a connected environment (see `audit/raw/phase-c10-db-validation.txt`).

---

## 2. Final architecture

**Client → Client Supplier → Supplier Reference Images**

- Persistence: `supplier_reference_images` (+ FK to client supplier).
- API: `/api/v3/clients/.../suppliers/.../reference-images` (+ `/file` for bytes/signed URL behavior).
- UI: Client detail supplier reference module / drawer.
- Pipeline: `client_supplier_id` on aisle → list supplier reference rows → `AnalysisContext.visual_references`.

---

## 3. Phase C completion map

| Phase | Outcome |
| ----- | ------- |
| C0 | Audit baseline |
| C1 | DB foundation `supplier_reference_images` |
| C2 | Supplier reference HTTP API |
| C3 | Frontend supplier reference UI |
| C4 | Legacy dependency audit |
| C5 / C5.1 | Dry-run analyzer + strict DB gate |
| C6 / C7 | NO_OP migration confirm + pipeline switch to supplier resolver |
| C8 | Legacy writes disabled; inventory UI hidden |
| C9 | Legacy system removal + guarded drop migration **0029** + test/doc updates |
| **C10** | Closure grep classification, validation logs, manual QA checklist, docs |

---

## 4. Backend final state

- **Table:** `supplier_reference_images` canonical; `inventory_visual_references` dropped after **0029** apply (still named in historical migrations **0002–0005** only).
- **API:** Supplier routes in `api/routes/v3/clients.py`; no inventory `visual-references` routes.
- **Use cases / repos:** Supplier upload/manage/list/get/delete + SQL/memory repos; no `InventoryVisualReference*` port.
- **Pipeline:** `SupplierReferenceImageResolver`; tests assert no legacy inventory visual-reference repo `list_by_inventory` on aisle path.

---

## 5. Frontend final state

- Supplier reference UX on **ClientDetail**; inventory pages do not host legacy reference management.
- **CreateInventoryDialog:** single-step creation; unused wizard copy removed from i18n (C10).
- Legacy client functions (`uploadInventoryVisualReferences`, etc.) **removed**.

---

## 6. Pipeline final state

**aisle.client_supplier_id** → **supplier_reference_images** → **`AnalysisContext.visual_references`** → job input / provider attachments → **`reference_usage`** in metadata where applicable.

---

## 7. Legacy removal state

| Artifact | State |
| -------- | ----- |
| `inventory_visual_references` | Removed by migration **0029** when empty; historical migrations unchanged |
| Legacy inventory visual-reference API | **Removed** (404 on old paths) |
| Legacy inventory UI | **Removed** |
| Legacy use cases / repos / domain | **Removed** (C9) |
| Legacy analyzer scripts | **Retained** for audit/reporting (`scripts/analyze_legacy_reference_migration.py`) |
| Tests | Legacy suites deleted; removal asserted by `test_inventory_visual_references_removed.py` |

---

## 8. Historical compatibility

- **`visual_reference_context`** / **`reference_usage`** / **`VisualReferenceContext`** remain part of runtime and historical JSON.
- Execution logs may still show **`visual_reference_attachments`** for supplier-backed runs.
- Old bookmarked inventory `/visual-references` URLs **404**.

---

## 9. Validation results

| Layer | Result |
| ----- | ------ |
| Backend pytest (supplier + pipeline subset) | **78 passed** |
| Backend pytest collect + ruff | **1979 tests collected**, **ruff clean** |
| Backend hybrid prompt profile tests | **5 passed** |
| Frontend typecheck / lint / build / full Vitest | **493 tests passed** |
| DB migrate status/validate | **Not run** (SQL timeout) — see raw log |

Artifacts: `audit/raw/phase-c10-validation-commands.txt`, `phase-c10-db-validation.txt`, `phase-c10-api-contract-check.md`, `phase-c10-remaining-reference-grep.md`.

---

## 10. Remaining observations

1. **Run `db_migrate.py status` / `validate` (and apply 0029 if pending)** in each deployment environment.
2. **Optional C9.x:** orphan blobs under historical inventory visual-reference prefixes — separate approved cleanup if needed.
3. **Product policy (future):** whether aisle processing should hard-require `client_supplier_id` when operators expect references (currently zero refs if null).

---

## 11. Risks accepted

- **DB connectivity not re-verified** in closure sandbox; mitigated by static migration tests + operator checklist.
- Prompt body wording in `hybrid_profiles.py` was aligned to “supplier” phrasing (semantic role unchanged: context-only references).

---

## 12. Recommended post-Phase-C work

- Optional orphaned storage scan/deletion (explicit phase).
- Stricter validation UX when aisle lacks supplier but operators expect reference images.
- Supplier image metadata UX polish (labels/descriptions already supported on API).

---

## Documents produced (C10)

- `audit/phase-c10-final-closure.md` (this file)
- `audit/phase-c10-manual-qa-checklist.md`
- `audit/raw/phase-c10-remaining-reference-grep.md`
- `audit/raw/phase-c10-db-validation.txt`
- `audit/raw/phase-c10-api-contract-check.md`
- `audit/raw/phase-c10-validation-commands.txt`
- `audit/raw/phase-c10-docs-reference-search.txt`
- `docs/reference-images.md`
- `backend/README.md` (supplier-scoped smoke steps)
