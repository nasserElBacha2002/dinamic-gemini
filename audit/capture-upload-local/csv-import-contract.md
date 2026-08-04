# CSV import contract (backend) — LOCAL_CSV_IMPORT

## Endpoints (v3, auth admin)

- `POST /{inventory_id}/local-csv-imports/preview`
- `POST /{inventory_id}/local-csv-imports/confirm`
- `GET /{inventory_id}/local-csv-imports/{import_id}`

## Flags

- `SERVER_CSV_IMPORT_ENABLED` (default **false**)
- Límite de tamaño configurable (default 5MB)

## Persistencia

Migración SQL Server `0074_local_csv_imports.sql` + repos memory/SQL.

## Garantías

- Idempotencia por `export_id` y secundaria `capture_session_id+capture_photo_id`
- No crea source assets / fotos falsas
- Origen marcado `LOCAL_CSV_IMPORT`
- Preview no confirma

Tests: `backend/tests/unit/test_local_csv_import.py`
