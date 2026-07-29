# Phase 2 Corrections — Implementation Report

## Status

Corrections applied for Phase 2 review findings + Phase 1 SQL IT validation.
Phase 3 was **not** started. OCR / CODE_SCAN / prompts / extraction logic unchanged.

## Fixes applied

1. **Mandatory `AccessPrincipal` + `InventoryAccessPolicy`** for user-facing upload/list/delete/process (and capture staging upload). No optional `AuthUser | None` / optional policy on those use cases.
2. **Capture session hierarchical auth** via `require_capture_session_upload_scope` before application spool; use case repeats policy (defense in depth).
3. **Public `RepositoryBackendStatus`** + `/health` diagnostics + `/ready` 503 when SQL required / resolution unhealthy / schema incompatible.
4. **Memory policy aliases** (`prod`/`production`/`stage`/`staging`/`uat`/`preprod`/`preproduction`) + explicit `V3_RUNTIME_ENVIRONMENT` / `DINAMIC_RUNTIME_PROFILE` preferred over pytest env heuristics.
5. **SoT consumer matrix** documented; contractual tests expanded; FE keeps `resolveBrowseRunJobIds` + `visibleJobId` / explicit / operational distinction.
6. **Gitignore** for `phase2-source-of-truth-security-*.txt` dumps (not versioned).
7. **Phase 1 SQL IT** executed against local SQL Server with migration `0071` present (`claim_owner_id`).
8. SQL test cleanup deletes `position_manual_image_coverage` / asset child tables before parents (unblocks full-suite integration cleanup on complete schemas).

## Phase 1 SQL validation record

| Item | Value |
|------|--------|
| SQL Server | Microsoft SQL Server 2022 (RTM-CU24) 16.0.4245.2 (Linux) |
| ODBC driver | ODBC Driver 17 for SQL Server |
| Migration | `0071_inventory_jobs_claim_owner_id.sql` (`claim_owner_id VARCHAR(64) NULL`) |
| Test DB | `dinamic_inventory_test` (schema cloned from local `dinamic-gemini`, set `READ_WRITE`) |
| Command | `backend/.venv/bin/python -m pytest backend/tests/integration/jobs/test_sql_atomic_job_claim.py -q --no-cov` |
| Result | **3 passed** (dual claim, dual stale reclaim, invalid aisle rollback) |
| Exit code | **0** |

## Authorization matrix (user-facing)

| Operation | Route dependency | Use-case policy | Cross-client |
|-----------|------------------|-----------------|--------------|
| Upload aisle assets | `require_inventory_client_scope` (before spool) | `require_aisle` | 404 |
| List/file/preview/delete assets | `require_inventory_client_scope` | `require_aisle` | 404 |
| Start process | `require_inventory_client_scope` | `require_aisle` + required `principal` | 404 |
| Capture staging upload | `require_capture_session_upload_scope` (hierarchy) | same policy again | 404 |

## Pre-spool behavior (documented)

FastAPI may still bind `UploadFile` objects when multipart is present. Corrections assert **application spool** (`_upload_files_to_staging_dtos` / `read_uploaded_files_for_aisle_asset_upload`) + storage/DB writes are zero when hierarchical/client auth raises. See `upload-authorization-matrix.md` and `test_capture_session_upload_prespool_auth_phase2.py`.

## Health / readiness

- `/health`: liveness `ok=true` + `repository_backend_resolved` / `healthy` / `reason_code` via public status API (no private `_get_repository_backend_resolution` from routes).
- `/ready`: 503 on schema incompatible or unresolved/unhealthy repository backend when SQL is required.

## Limitations

- Observability job-read helpers may still accept `AuthUser` via `ResolveAisleJobForInventoryReadUseCase` (follow-up: migrate to `AccessPrincipal`).
- Fresh `schema.sql` bootstrap alone remains order-sensitive for empty DBs; local validation used a cloned schema + `0071`.
- Aisle-asset dependency only checks inventory client scope; aisle ownership is enforced in the use case (may spool multipart once, still zero storage/DB on deny).

## Validation commands (exit codes)

| Command | Result |
|---------|--------|
| Phase 1 SQL IT (`test_sql_atomic_job_claim.py`) | 3 passed, exit 0 |
| Targeted Phase 2 suites (SoT, upload scope, memory, health/ready, pre-spool) | 50 passed, exit 0 |
| Full backend pytest | 3897 passed, 16 skipped, **5 failed** (unrelated `test_sql_supplier_prompt_config_repository` — client id longer than `VARCHAR(36)` on cloned schema) |
| Ruff `backend scripts` | All checks passed, exit 0 |
| Mypy via Quality Gate / pyproject | OK in gate |
| Frontend typecheck/lint/test | exit 0 (1221 tests) |
| Mobile typecheck/lint/test | exit 0 (139 + 10 migration tests) |
| `enforce_quality_gate.py --strict` | **PASS**, exit 0 |

## Mergeability

**Mergeable with warnings:** mandatory Phase 1/2 suites green; FE/mobile/QG green. Full backend suite still has 5 pre-existing-style SQL supplier-prompt IT failures on long synthetic client ids (not introduced by AccessPrincipal / SoT / health changes).
