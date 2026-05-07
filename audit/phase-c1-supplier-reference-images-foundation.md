# C1 — Supplier Reference Images Backend Foundation

## 1. Executive summary
Status:
- READY_WITH_OBSERVATIONS

C1 backend foundation for supplier-level reference images was implemented additively, reusing existing storage/repository/use-case patterns and preserving legacy inventory-scoped visual references and pipeline behavior.

## 2. Scope implemented
- Added additive persistence foundation (`supplier_reference_images`) via migration and schema snapshot sync.
- Added `SupplierReferenceImage` domain entity with basic invariants.
- Added `SupplierReferenceImageRepository` application port.
- Added SQL + in-memory repository implementations.
- Added list/upload/delete use cases with mandatory client/supplier ownership chain validation:
  - `client_id` exists
  - `supplier_id` exists
  - `supplier.client_id == client_id`
  - `image.client_supplier_id == supplier_id` (delete)
- Reused existing `ArtifactStorage` pattern including provider metadata and best-effort file cleanup.
- Added runtime and API dependency wiring for the new repository/use cases.
- Added focused backend tests (domain/use case/repository/migration).

## 3. Files changed
- `backend/src/database/migrations/versions/0028_supplier_reference_images.sql` — additive migration.
- `backend/src/database/schema.sql` — canonical schema sync for new table/index/FK.
- `backend/src/domain/client_supplier/reference_image.py` — new domain model.
- `backend/src/application/ports/repositories.py` — new repository port.
- `backend/src/application/errors.py` — `SupplierReferenceImageNotFoundError`.
- `backend/src/application/utils/supplier_reference_image_paths.py` — supplier image storage path helper.
- `backend/src/application/use_cases/upload_supplier_reference_images.py` — list + upload use cases.
- `backend/src/application/use_cases/manage_supplier_reference_images.py` — delete use case.
- `backend/src/infrastructure/repositories/sql_supplier_reference_image_repository.py` — SQL implementation.
- `backend/src/infrastructure/repositories/memory_supplier_reference_image_repository.py` — in-memory implementation.
- `backend/src/runtime/app_container.py` — container wiring.
- `backend/src/runtime/v3_deps.py` — dependency getter wiring.
- `backend/src/api/dependencies.py` — use case dependency providers (no route activation yet).
- `backend/tests/domain/test_supplier_reference_image_entity.py` — domain invariants.
- `backend/tests/application/use_cases/test_upload_supplier_reference_images.py` — upload/list behavior and validations.
- `backend/tests/application/use_cases/test_manage_supplier_reference_images.py` — delete behavior and ownership checks.
- `backend/tests/infrastructure/repositories/test_memory_supplier_reference_image_repository.py` — memory repository behavior.
- `backend/tests/infrastructure/repositories/test_sql_supplier_reference_image_repository_unit.py` — SQL row mapping behavior.
- `backend/tests/database/test_migration_0028_supplier_reference_images.py` — migration/schema presence assertions.

## 4. Database changes
- New additive migration `0028_supplier_reference_images.sql`.
- Added table `supplier_reference_images` with required metadata fields.
- Added FK `FK_supplier_reference_images_client_supplier` (`client_supplier_id -> client_suppliers.id`).
- Added index `IX_supplier_reference_images_client_supplier_id`.
- No drops or destructive migration operations.

## 5. Domain/repository/use case design
- Domain:
  - `SupplierReferenceImage` mirrors existing visual reference metadata fields with supplier scope and `label`/`description`.
- Repository port:
  - `get_by_id`, `create`, `create_many`, `list_by_supplier`, `delete`.
- SQL repository:
  - Parameterized SQL inserts/selects/deletes.
  - Provider metadata mapping aligned with existing storage-field resolution behavior.
- Memory repository:
  - In-memory parity with ordering (`created_at ASC, id ASC`) and idempotent delete.
- Use cases:
  - `ListSupplierReferenceImagesUseCase`
  - `UploadSupplierReferenceImagesUseCase`
  - `DeleteSupplierReferenceImageUseCase`

## 6. Ownership validation
- Implemented in use cases (not hidden in low-level SQL):
  - Client existence check (`ClientNotFoundError`)
  - Supplier existence check (`ClientSupplierNotFoundError`)
  - Supplier-client ownership check (`ClientSupplierClientMismatchError`)
  - Image-supplier ownership check on delete (`SupplierReferenceImageNotFoundError` when out of scope)

## 7. Storage integration
- Reused existing `ArtifactStorage` abstraction.
- Upload path helper:
  - `client_suppliers/{client_supplier_id}/reference_images/{reference_image_id}.{ext}`
- Reused provider metadata recording (`storage_provider`, `storage_bucket`, `storage_key`, `content_type`, `file_size_bytes`, `etag`).
- Upload rollback behavior: if DB write fails after file writes, perform best-effort file cleanup in reverse order.
- Delete behavior: DB delete + best-effort artifact delete, aligned with existing inventory visual reference pattern.

## 8. Tests added
- Domain:
  - `test_supplier_reference_image_entity.py`
- Use cases:
  - `test_upload_supplier_reference_images.py`
  - `test_manage_supplier_reference_images.py`
- Repositories:
  - `test_memory_supplier_reference_image_repository.py`
  - `test_sql_supplier_reference_image_repository_unit.py`
- Migration/schema:
  - `test_migration_0028_supplier_reference_images.py`

## 9. Validation commands
Executed:
- `backend/.venv/bin/python -m pytest <targeted C1 tests>`
  - Result: PASS
- `backend/.venv/bin/python -m pytest --collect-only`
  - Result: PASS (collection successful)
- `backend/.venv/bin/python -m ruff check backend/src backend/tests`
  - Result: PASS
- `backend/.venv/bin/python backend/scripts/db_migrate.py status`
  - Result: FAIL (environment: SQL Server HYT00 login timeout)
- `backend/.venv/bin/python backend/scripts/db_migrate.py validate`
  - Result: FAIL (environment: SQL Server HYT00 login timeout)

## 10. Out-of-scope preserved
- Pipeline unchanged: confirmed.
- `inventory_visual_references` behavior unchanged: confirmed.
- Prompts unchanged: confirmed.
- Frontend unchanged: confirmed.
- No legacy reference migration/copy performed: confirmed.

## 11. Observations / blockers
- SQL migration runtime validation remains environment-blocked by SQL Server connectivity (`HYT00` login timeout).
- C1 backend foundation is code-complete and test-validated with local/unit coverage; DB status/validate should be rerun once connectivity is restored.

## 12. Recommended next phase
- C2 — Backend API contract and validations
