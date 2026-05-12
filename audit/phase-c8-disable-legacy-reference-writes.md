# C8 — Disable Legacy Reference Writes and Hide Old UI

## 1. Executive summary

**Status:** `READY_WITH_OBSERVATIONS`

C8 disables inventory-scoped visual reference **writes** at the v3 API route layer (410 + structured `LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED`), keeps **GET list** and **GET file** for temporary compatibility, and removes the operational entry points from **InventoryDetail** and from the **create inventory** wizard. Supplier reference images remain the canonical management path.

**Observation:** Local backend pytest in this environment failed to import the app under **Python 3.9** (`Settings | None` typing). Validation should be run with **Python 3.11+** as required by the project.

---

## 2. Scope implemented

- Backend: POST / PUT / DELETE on `/api/v3/inventories/{inventory_id}/visual-references` return **410 Gone** with structured error body.
- Frontend: No legacy reference-images module/button on inventory detail; create-inventory flow no longer includes reference upload or calls `uploadInventoryVisualReferences`.

---

## 3. Backend behavior

| Endpoint | Behavior |
|----------|-----------|
| `GET /api/v3/inventories/{inventory_id}/visual-references` | Unchanged — lists references when inventory exists. |
| `GET /api/v3/inventories/{inventory_id}/visual-references/{reference_id}/file` | Unchanged — resolves file / redirect. |
| `POST .../visual-references` | **410** — `code`: `LEGACY_INVENTORY_VISUAL_REFERENCES_DISABLED`; English `detail` points operators to supplier reference images. |
| `PUT .../visual-references/{reference_id}` | **410** — same structured body. |
| `DELETE .../visual-references/{reference_id}` | **410** — same structured body. |

Use cases and repositories for legacy inventory visual references are **not** removed (C9 cleanup).

---

## 4. Frontend behavior

- **InventoryDetail:** `InventoryReferenceImagesModule` and the header “referencias visuales” action were removed; aisles and other flows unchanged.
- **Create inventory:** Single-step wizard ( datos del inventario only ); no drag-drop reference step; `useCreateInventoryFlow` only performs `POST /inventories`.

---

## 5. Supplier canonical path

Supplier reference image API and ClientDetail supplier UI were **not** modified for C8; they remain the operational surface for reference images.

---

## 6. Legacy compatibility retained

- Table `inventory_visual_references` unchanged.
- Legacy read/list/file routes retained.
- No bulk deletion of legacy rows or storage objects in C8.

---

## 7. Tests updated

| Area | File |
|------|------|
| Backend API | `backend/tests/api/test_inventory_visual_references_api.py` — 410 on writes; seed data via `UploadInventoryVisualReferencesUseCase` for read/file tests. |
| Frontend inventory detail | `frontend/tests/InventoryDetailPage.test.tsx` — removed drawer/lazy-ref hooks; asserts header no longer exposes legacy reference control. |
| Frontend create inventory | `frontend/tests/CreateInventoryDialog.visualReferences.test.tsx` — single-step flow; asserts `uploadInventoryVisualReferences` is never called. |

---

## 8. Validation commands

Commands **intended** (run locally with Python **3.11+** for backend):

```bash
cd backend
python3 -m pytest tests/api/test_inventory_visual_references_api.py -q --no-cov
python3 -m pytest tests/api/test_supplier_reference_images_api.py -q --no-cov
python3 -m ruff check src tests scripts

cd ../frontend
npm run typecheck
npm run lint
npm run build
npm test -- --run
npm test -- InventoryDetailPage --run
npm test -- CreateInventoryDialog.visualReferences --run
```

**Results (agent run):**

| Command | Result |
|---------|--------|
| `npm run typecheck` (frontend) | Pass |
| `npm run lint` (frontend) | Pass |
| `npm run build` (frontend) | Pass |
| `vitest` InventoryDetailPage + CreateInventoryDialog.visualReferences | Pass (28 tests) |
| `vitest` ClientDetailPage + SupplierReferenceImagesModule | Pass (9 tests) |
| `ruff check` on touched backend files | Pass |
| `pytest` API inventory visual references | **Not run** — workspace default `python3` is **3.9.6**; app import fails on PEP604 unions in auth settings. Use **Python 3.11+** per project standard. |

---

## 9. Boundaries preserved

- `inventory_visual_references` table not dropped.
- Legacy GET list + GET file retained.
- Supplier API/UI unchanged by this phase.
- Pipeline supplier-reference resolution unchanged (no edits to executor/resolver in C8).
- No migration/copy/delete of stored reference files for C8.
- No prompt changes.

---

## 10. Observations / blockers

- **Python version:** Use 3.11+ for backend tests and CI parity with project standards.
- **DELETE decorator:** Route no longer advertises `204`; clients calling DELETE receive **410** with JSON body (structured handler).

---

## 11. Recommended next phase

**C9 — Remove legacy inventory reference system** (drop unused routes/use cases/repos/table when product approves, after monitoring).
