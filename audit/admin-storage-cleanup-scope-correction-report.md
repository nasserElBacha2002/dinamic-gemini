# Admin storage cleanup — scope correction report

## 1. Executive summary

**Status:** `CLEANUP_SCOPE_HARDENED`

Admin storage cleanup no longer deletes entire `output/v3_uploads` or the configured remote bucket prefix (`v3/`). Deletion is limited to inventory-operational allowlist prefixes, with explicit protection for supplier/client-supplier reference images.

## 2. Root cause

The first implementation treated `v3_uploads` (local) and the full configured GCS/S3 prefix (remote) as safe deletion roots. That space mixes:

- **Operational inventory uploads** (aisle assets, capture staging, job durable outputs)
- **Long-lived configuration** (e.g. `client_suppliers/{id}/reference_images/{id}.jpg`)

A broad cleanup removed supplier reference files while DB rows still pointed at them, causing pipeline errors such as:

```text
visual reference 065b9151-ed44-4377-94ba-41e79894a0b3: local provider file not found at
.../v3_uploads/client_suppliers/f7f2b112-ad3e-48d0-aa03-aa95dceff896/reference_images/065b9151-ed44-4377-94ba-41e79894a0b3.jpg
```

## 3. Protected asset classes

Never deleted by admin inventory cleanup:

- Client supplier reference images (`client_suppliers/**/reference_images/**`)
- Supplier reference image libraries (`supplier_reference_images/`)
- Any path containing `/reference_images/` as a protected segment
- Paths outside inventory-operational allowlist prefixes

## 4. New deletion model

1. **Allowlist first** — only scan/delete under:
   - `uploads/` (aisle source assets)
   - `capture/staging/` (or `V3_CAPTURE_STAGING_STORAGE_PREFIX`)
   - `jobs/` (durable worker artifacts)
   - Optional local pipeline temp: `output/{job_id}/run/` (not under `v3_uploads`)
2. **Protected-prefix second** — any candidate matching `client_suppliers/`, `supplier_reference_images/`, or `/reference_images/` is skipped.
3. **Remote** — list only allowlisted sub-prefixes under the configured bucket prefix; never `list_blobs(prefix="v3/")` + delete all.
4. **Confirmation** — delete mode requires `DELETE_INVENTORY_ARTIFACTS`.

## 5. Files changed

| Area | File |
| --- | --- |
| Maintenance engine | `backend/src/infrastructure/storage/artifact_storage_maintenance.py` |
| Use case | `backend/src/application/use_cases/admin_storage_cleanup.py` |
| API schemas / route | `backend/src/api/schemas/admin_storage_cleanup_schemas.py`, `backend/src/api/routes/v3/admin_storage.py` |
| Tests | `backend/tests/infrastructure/storage/test_artifact_storage_maintenance.py`, `backend/tests/api/test_admin_storage_cleanup_api.py` |
| Frontend | `frontend/src/pages/AdminStorageMaintenancePage.tsx`, `frontend/src/api/adminStorageApi.ts`, i18n ES/EN, `frontend/tests/AdminStorageMaintenancePage.test.tsx` |
| Recovery audit | `scripts/audit_missing_supplier_reference_images.py`, `audit/missing-supplier-reference-images-report.md` |

## 6. Tests added

- Regression: `client_suppliers/f7f2b112-.../reference_images/065b9151-....jpg` must not be deleted (local + remote classification).
- Local delete removes `uploads/` files, preserves `client_suppliers/**`.
- Remote delete only targets allowlisted prefixes; supplier objects are not listed/deleted.
- Confirm token `DELETE_INVENTORY_ARTIFACTS`.

## 7. Validation commands

```bash
pytest backend/tests/infrastructure/storage/test_artifact_storage_maintenance.py backend/tests/api/test_admin_storage_cleanup_api.py -q
ruff check backend/src/infrastructure/storage/artifact_storage_maintenance.py backend/src/application/use_cases/admin_storage_cleanup.py
python -m compileall backend/src/infrastructure/storage
cd frontend && npm test -- AdminStorageMaintenancePage.test.tsx
```

## 8. Remaining risks

- Other long-lived prefixes under `v3_uploads` not yet classified (if added in future) need explicit allowlist/protected rules before any global cleanup.
- Per-inventory scoped cleanup endpoint (`POST .../cleanup/inventory/{id}`) was not added; global cleanup remains allowlist-filtered only.
- Pipeline temp `output/{job}/run/` deletion is optional and still broad within that folder.

## 9. Recovery status

- Missing supplier reference report: `audit/missing-supplier-reference-images-report.md` (generate with `python scripts/audit_missing_supplier_reference_images.py` when SQL Server is available).
- **Recovery performed:** no (read-only audit).
- **Manual action:** re-upload or restore the known missing reference image for client supplier `f7f2b112-ad3e-48d0-aa03-aa95dceff896`.
