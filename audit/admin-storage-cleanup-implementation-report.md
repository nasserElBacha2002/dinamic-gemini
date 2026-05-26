# Admin storage cleanup — implementation report

## Executive summary

**Status:** `IMPLEMENTED`

Admin-only destructive cleanup for remote bucket objects (GCS/S3, configured prefix only) and safe local roots (`output/v3_uploads`, optional `output/{job}/run`). Backend enforces primary administrator principal; frontend hides the panel from non-admin users.

## What changed

| Area | Files |
|------|--------|
| Maintenance engine | `backend/src/infrastructure/storage/artifact_storage_maintenance.py` |
| Use case | `backend/src/application/use_cases/admin_storage_cleanup.py` |
| API schemas | `backend/src/api/schemas/admin_storage_cleanup_schemas.py` |
| API route | `backend/src/api/routes/v3/admin_storage.py` |
| Server wiring | `backend/src/api/server.py` |
| Backend tests | `backend/tests/infrastructure/storage/test_artifact_storage_maintenance.py`, `backend/tests/api/test_admin_storage_cleanup_api.py` |
| Frontend API | `frontend/src/api/adminStorageApi.ts`, `frontend/src/api/client.ts` |
| Frontend page | `frontend/src/pages/AdminStorageMaintenancePage.tsx` |
| Routes/nav/i18n | `frontend/src/App.tsx`, `appRoutes.ts`, `navConfig.tsx`, `AppShell.tsx`, `es/en/translation.json` |
| Frontend tests | `frontend/tests/AdminStorageMaintenancePage.test.tsx` |

## Security model

- **Frontend:** Panel only when `user.username === 'admin'` (`RequireUsernameAdmin`).
- **Backend:** `POST /api/v3/admin/storage/cleanup` uses `require_ai_config_inspection_user` (primary `AuthUser.id == "admin"`). Jairo and unauthenticated callers get **403** / **401**.
- **No client paths:** Local roots are derived from `OUTPUT_DIR` settings only.
- **Remote guard:** Empty GCS/S3 prefix → remote cleanup skipped (no bucket-wide delete).
- **Dry-run default:** API defaults `mode=dry_run`; delete requires `confirm=DELETE_ARTIFACTS`.
- **Logging:** Counts and paths only; no credentials or signed URLs.

## Cleanup behavior

### Remote (`target` includes `remote`)

- Uses configured `ARTIFACT_STORAGE_PROVIDER` (`gcs` or `s3`).
- Lists/deletes only under configured prefix (e.g. `v3/`).
- `provider=local` → remote section skipped.

### Local (`target` includes `local`)

- Default root: `{OUTPUT_DIR}/v3_uploads`.
- Optional: `{OUTPUT_DIR}/{job_id}/run` when `include_pipeline_temp=true`.
- Does **not** delete entire `output/`, `.env`, `secrets/`, or source tree.

## Tests run

| Command | Result |
|---------|--------|
| `pytest tests/infrastructure/storage/test_artifact_storage_maintenance.py tests/api/test_admin_storage_cleanup_api.py -q --noconftest` | **9 passed** |
| `npm test -- --run tests/AdminStorageMaintenancePage.test.tsx` | **2 passed** |
| `ruff check` (new backend modules) | **Pass** |

## Manual test checklist

1. Login as non-admin → no maintenance nav item / panel.
2. Direct `POST /api/v3/admin/storage/cleanup` as Jairo → **403**.
3. Login as admin → **Mantenimiento de archivos** in sidebar.
4. **Simular limpieza** → summary only (no deletes).
5. Delete without `DELETE_ARTIFACTS` → **400**.
6. Delete with confirmation → removes only prefix-scoped remote objects and allowed local roots.
7. Verify bucket objects outside prefix remain.
8. Verify `output/` root files (non-v3_uploads) remain unless under optional pipeline temp.

## Next step

Run a **production-like dry-run** against the real GCS bucket, review counts, then execute delete only if intentional. Consider Phase 6 backfill before mass delete of legacy local files still referenced in SQL.
