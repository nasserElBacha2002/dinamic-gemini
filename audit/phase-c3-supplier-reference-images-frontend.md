# C3 — Supplier Reference Images Frontend

## 1. Executive summary

**Status:** READY_FOR_C4 (C3.1 review fixes applied)

The frontend consumes the C2 supplier reference images API: typed client helpers, scoped React Query keys and hooks, and a **Cliente → Proveedores** workflow on `ClientDetail` that opens a drawer to list, upload (single file per action with optional etiqueta/descripción), preview via authenticated `GET …/file` (blob through `protectedFetch`), and delete with confirmation. Inventory visual references UI is unchanged aside from a non-breaking optional extension on `ManagedImageAssetsDrawer`. Backend and pipeline were not modified.

---

## 2. Scope implemented

| Area | Delivered |
|------|-----------|
| Types | `SupplierReferenceImage`, list/upload/delete responses; `UploadSupplierReferenceImagesRequest` |
| Paths | `supplierReferenceImagesPath`, `supplierReferenceImagePath`, `supplierReferenceImageFilePath` in `v3ApiPaths.ts` |
| API client | `listSupplierReferenceImages`, `uploadSupplierReferenceImages`, `deleteSupplierReferenceImage`, `getSupplierReferenceImageFileUrl`, `fetchSupplierReferenceImageFile` in `clientSuppliersApi.ts`; re-exported from `api/client.ts` |
| Query keys | `queryKeys.clients.suppliers.referenceImages(clientId, supplierId)` |
| Hooks | `useSupplierReferenceImages`; `useUploadSupplierReferenceImages`; `useDeleteSupplierReferenceImage` (invalidates scoped reference-images key) |
| UI | `SupplierReferenceImagesModule` + `SupplierReferenceImagesDrawer` (`ManagedImageAssetsDrawer` adapter); `ClientDetail` column **Referencias** / **Gestionar imágenes** |
| i18n | Spanish keys under `clients.suppliers.reference_images.*` |
| Tests | API/path/FormData tests; module smoke test; `ClientDetailPage` interaction test |

**Deferred:** PUT replace; activating supplier images in CV pipeline; multi-file upload in UI (backend supports multi — drawer uses `uploadMultiple={false}` and copy explains optional metadata).

---

## 3. Files changed

| File | Role |
|------|------|
| `frontend/src/constants/v3ApiPaths.ts` | Path builders |
| `frontend/src/api/types/responses.ts` | Supplier reference image DTOs |
| `frontend/src/api/types/requests.ts` | `UploadSupplierReferenceImagesRequest` |
| `frontend/src/api/clientSuppliersApi.ts` | List/upload/delete/file fetch & URL helper |
| `frontend/src/api/client.ts` | Barrel exports |
| `frontend/src/api/queryKeys.ts` | `referenceImages(clientId, supplierId)` |
| `frontend/src/hooks/useClients.ts` | `useSupplierReferenceImages` |
| `frontend/src/hooks/useMutations.ts` | Upload/delete mutations + invalidation |
| `frontend/src/hooks/index.ts` | Export hooks |
| `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx` | Optional `uploadExtras`, `uploadMultiple` (defaults preserve inventory behavior) |
| `frontend/src/features/clients/hooks/useSupplierReferencePreview.ts` | Preview fetch for supplier `/file` |
| `frontend/src/features/clients/components/SupplierReferenceImagesDrawer.tsx` | Spanish copy + metadata fields + `ManagedImageAssetsDrawer` |
| `frontend/src/features/clients/components/SupplierReferenceImagesModule.tsx` | Query + mutations + snackbars |
| `frontend/src/pages/ClientDetail.tsx` | Supplier row action + module mount |
| `frontend/src/i18n/locales/es/translation.json` | New strings |
| `frontend/tests/clientSuppliersReferenceImagesApi.test.ts` | Paths, URL suffix, FormData |
| `frontend/tests/SupplierReferenceImagesModule.test.tsx` | Drawer render |
| `frontend/tests/ClientDetailPage.test.tsx` | Extended mocks + open drawer flow |

---

## 4. API contract consumed

| Method | Path |
|--------|------|
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` |
| POST | same (multipart `files`, optional `label`, `description`) |
| DELETE | `…/reference-images/{image_id}` |
| GET | `…/reference-images/{image_id}/file` (preview/download via `fetch` + blob URL; redirects followed by `fetch`) |

Frontend assumes JSON responses match C2 (no storage internals). `getSupplierReferenceImageFileUrl` exposes the relative URL shape for diagnostics/links; preview uses `fetchSupplierReferenceImageFile` so Bearer auth applies.

---

## 5. UI behavior

1. On **ClientDetail**, each supplier row has **Gestionar imágenes**.
2. Opens drawer: lazy list query (`enabled` only when drawer open).
3. Empty / loading / error states reuse drawer patterns.
4. Upload: single file input; optional etiqueta y descripción; success snackbar.
5. Preview: authenticated fetch → blob URL (same strategy as inventory references).
6. Delete: confirmation dialog; success snackbar; list refreshes via query invalidation.

---

## 6. React Query behavior

- **Key:** `['v3','clients','suppliers', clientId, 'reference-images', supplierId]`
- **Invalidation:** After successful upload and delete mutations for that `(clientId, supplierId)`.
- Supplier reference cache is separate from `queryKeys.inventories.visualReferences`.

---

## 7. i18n

All new visible strings live under `clients.suppliers.reference_images` (Spanish). Inventory `reference_drawer` keys were not changed.

---

## 8. Tests added

- **`clientSuppliersReferenceImagesApi.test.ts`** — path encoding; file URL suffix alignment; FormData `files` / trimmed label & description.
- **`SupplierReferenceImagesModule.test.tsx`** — drawer title / empty copy (Spanish).
- **`ClientDetailPage.test.tsx`** — “Gestionar imágenes” visible with suppliers; click opens drawer text.

---

## 9. Validation commands

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run build` | Pass |
| `npm test -- --run ClientDetailPage SupplierReferenceImagesModule clientSuppliersReferenceImagesApi` | Pass |
| `pytest tests/api/test_supplier_reference_images_api.py` (backend sanity) | Pass |

---

## 10. Boundaries preserved

- Backend unchanged: **yes**
- Pipeline unchanged: **yes**
- `inventory_visual_references` behavior unchanged: **yes** (inventory drawer unchanged; shared drawer only gained optional props with safe defaults)
- Prompts unchanged: **yes**
- No legacy migration/copy: **yes**
- PUT replace not implemented: **yes**

---

## 11. Observations / blockers

- Full `npm test -- --run` executed in C3.1; pass (see C3.1 validation table).
- Multi-file upload remains available server-side; UI intentionally single-select to avoid ambiguous batch metadata unless product asks for multi + batch notice.
- Vitest logs an existing MUI `DialogTitle` / `Typography` nesting warning when opening `ImagePreviewDialog` from tests; behavior matches production Reference Images coverage.

---

## 12. Recommended next phase

**C4 — Legacy coexistence hardening / regression review** (coexistence of supplier vs inventory references, docs, optional pipeline activation when approved).

---

## C3.1 Review fixes

Small UX and test hardening before C4; backend, pipeline, prompts, and inventory visual references behavior unchanged.

### UX fixes

- After a **successful** supplier reference upload, **Etiqueta** and **Descripción** are cleared. Failed uploads leave the fields intact.
- `SupplierReferenceImagesModule.handleUpload` no longer swallows `mutateAsync` errors (removed empty `catch`), so the drawer’s upload wrapper only clears metadata when the mutation resolves successfully.

### Tests added

| File | Coverage |
|------|----------|
| `frontend/tests/SupplierReferenceImagesDrawer.test.tsx` | Label/description input; `onUpload` receives files + metadata; `uploadMultiple=false` on file input; fields cleared on success, retained on rejection; delete confirmation calls `onDelete` with id |
| `frontend/tests/ManagedImageAssetsDrawer.previewRevoke.test.tsx` | Preview `revoke()` when dialog closes, when switching preview target, and on drawer unmount |
| `frontend/tests/useSupplierReferenceImageMutations.test.tsx` | Upload and delete mutations invalidate `queryKeys.clients.suppliers.referenceImages(clientId, supplierId)` |
| `frontend/tests/SupplierReferenceImagesModule.test.tsx` | List query `isError` shows Spanish `load_error` copy |

### Validation results

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run build` | Pass |
| `npm test -- --run` | Pass |
| `npm test -- SupplierReferenceImages --run` | Pass |
| `npm test -- ClientDetailPage --run` | Pass |

### Boundaries preserved

- Backend unchanged
- Pipeline unchanged
- Prompts unchanged
- `inventory_visual_references` behavior unchanged (shared drawer only exercised via existing revoke paths; no inventory-specific changes)
- No legacy migration/copy
- PUT replace not implemented
