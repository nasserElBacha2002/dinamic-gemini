# Missing supplier reference images — audit report

Generated: 2026-05-26T15:52:17.190102+00:00

## Database

Could not query `supplier_reference_images`: `('HYT00', '[HYT00] [Microsoft][ODBC Driver 17 for SQL Server]Login timeout expired (0) (SQLDriverConnect)')`

Run this script with SQL Server available (same env as the API) to populate the table.

## Known incident (manual)

| Reference image id | Client supplier id | Expected path/key | Exists local | Exists remote | Recommended recovery |
| --- | --- | --- | ---: | ---: | --- |
| 065b9151-ed44-4377-94ba-41e79894a0b3 | f7f2b112-ad3e-48d0-aa03-aa95dceff896 | `client_suppliers/f7f2b112-ad3e-48d0-aa03-aa95dceff896/reference_images/065b9151-ed44-4377-94ba-41e79894a0b3.jpg` | no (reported) | unknown | Re-upload via admin supplier reference UI or restore file under `/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/output/v3_uploads/...` |
