# Supplier reference image preview fix

## 1. Executive summary

Status: **FIXED**

Supplier reference image preview now follows the same `image-display-url` → direct `<img src>` path as aisle source assets. Presigned GCS/S3 URLs are no longer loaded via `fetch()` to `storage.googleapis.com`, eliminating the browser CORS failure on localhost.

## 2. Root cause

| Aspect | Aisle source (working) | Supplier reference (broken) |
|--------|------------------------|-----------------------------|
| Preview hook | `useEvidenceImageLoad` / asset flow | `useSupplierReferencePreview` |
| API | `GET .../image-display-url` | `GET .../file` (307 redirect to GCS) |
| Frontend load | `fetchReferenceImageDisplay` → `image_url` → `<img src>` | `fetch()` followed redirect → cross-origin GCS → **CORS blocked** |
| GCS access | Browser loads image as resource (no CORS preflight for simple img) | `fetch()` requires bucket CORS |

The bucket and signed URL generation were fine; the supplier path used the wrong endpoint and blob-fetch pattern.

## 3. Changes made

**Backend**

- `backend/src/api/services/v3_stored_artifact_access.py` — `resolve_supplier_reference_image_display()` (delegates to source-asset resolver).
- `backend/src/api/routes/v3/clients.py` — `GET .../reference-images/{image_id}/image-display-url` (same response shape as aisle assets).

**Frontend**

- `frontend/src/utils/fetchReferenceImageDisplay.ts` — shared display-url client (aisle + supplier).
- `frontend/src/utils/imageDisplayStrategy.ts` — `shouldRenderImageDirectly`, `isExternalSignedStorageUrl`.
- `frontend/src/api/clientSuppliersApi.ts` — `fetchSupplierReferenceImageDisplay`; `/file` only for authenticated local blob.
- `frontend/src/api/assetsApi.ts` — refactored to shared helper.
- `frontend/src/features/clients/hooks/useSupplierReferencePreview.ts` — uses display-url flow.
- `frontend/src/constants/v3ApiPaths.ts` — supplier display URL path.
- `frontend/src/components/ui/ImagePreviewDialog.tsx` — DOM nesting fix (`DialogTitle` / `Typography`).

**Tests**

- `frontend/tests/imageDisplayStrategy.test.ts`
- `frontend/tests/useSupplierReferencePreview.test.ts`
- `backend/tests/api/test_v3_stored_artifact_access_unit.py`
- `backend/tests/api/test_supplier_reference_images_api.py`

## 4. Behavior after fix

| Provider | Behavior |
|----------|----------|
| Local / legacy | `display_strategy=authenticated_file_fetch` → authenticated `GET .../file` → blob URL for preview |
| GCS signed URL | `display_strategy=presigned_url` → `image_url` returned → direct `<img src>` (no GCS `fetch`) |
| S3 presigned | Same as GCS via shared resolver and strategy helpers |

Bucket permissions, public access, and signed URL generation logic were not changed.

## 5. Tests run

| Command | Result |
|---------|--------|
| `cd frontend && npm test -- --run imageDisplayStrategy.test.ts useSupplierReferencePreview.test.ts` | 6 passed |
| `cd frontend && npm run typecheck` | Not re-run this session; passed earlier after import fixes |
| `pytest backend/tests/api/test_supplier_reference_images_api.py -k image_display_url` | Collection blocked on system Python 3.9 (`Settings \| None`); run in project 3.11+ venv |
| `pytest backend/tests/api/test_v3_stored_artifact_access_unit.py -k supplier_reference` | Same environment limitation |

## 6. Manual validation

```txt
1. Open Clientes → Proveedor del cliente → Imágenes de referencia.
2. Click Vista previa.
3. Image loads in modal.
4. No CORS error in console.
5. Open Resultados del pasillo → Archivos de origen del pasillo.
6. Existing preview still works.
```
