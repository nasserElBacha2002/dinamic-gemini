# DAST case matrix — dinamic-gemini (non-mutating initial)

**TOTAL_DAST_CASES:** 35
**estimated_requests:** 102

| Suite | Case ID | Method | Path | Param | Category | Source |
|---|---|---|---|---|---|---|
| health-and-ready | health-get | GET | `/health` |  | smoke | `backend/src/api/server.py` |
| health-and-ready | ready-get | GET | `/ready` |  | smoke | `backend/src/api/server.py` |
| input-validation | inventories-invalid-page | GET | `/api/v3/inventories/` |  | input_validation | `backend/src/api/routes/v3/inventories.py` |
| input-validation | inventories-invalid-uuid-status | GET | `/api/v3/inventories/` |  | input_validation | `backend/src/api/routes/v3/inventories.py` |
| input-validation | inventories-huge-page-size | GET | `/api/v3/inventories/` |  | input_validation | `backend/src/api/routes/v3/inventories.py` |
| input-validation | inventories-empty-search | GET | `/api/v3/inventories/` |  | input_validation | `backend/src/api/routes/v3/inventories.py` |
| input-validation | inventories-long-search | GET | `/api/v3/inventories/` |  | input_validation | `backend/src/api/routes/v3/inventories.py` |
| input-validation | client-invalid-uuid | GET | `/api/v3/clients/not-a-uuid` |  | input_validation | `backend/src/api/routes/v3/clients.py` |
| input-validation | review-queue-bad-confidence | GET | `/api/v3/review-queue/positions` |  | input_validation | `backend/src/api/routes/v3/review_queue.py` |
| input-validation | config-upload-limits | GET | `/api/v3/config/upload-limits` |  | input_validation | `backend/src/api/routes/v3/config.py` |
| sql-injection | sqli-inventories-search | GET | `/api/v3/inventories/` | search | sql_injection | `backend/src/api/routes/v3/inventories.py` |
| sql-injection | sqli-review-queue-sku | GET | `/api/v3/review-queue/positions` | sku_contains | sql_injection | `backend/src/api/routes/v3/review_queue.py` |
| sql-injection | sqli-position-labels-search | GET | `/api/v3/clients/11111111-1111-4111-8111-111111111111/position-labels` | search | sql_injection | `backend/src/api/routes/v3/client_position_labels.py` |
| sql-injection | sqli-aisle-locations-search | GET | `/api/v3/inventories/33333333-3333-4333-8333-333333333333/aisles/44444444-4444-4444-8444-444444444444/locations` | search | sql_injection | `backend/src/api/routes/v3/aisle_locations.py` |
| sql-injection | sqli-positions-sku-filter | GET | `/api/v3/inventories/33333333-3333-4333-8333-333333333333/aisles/44444444-4444-4444-8444-444444444444/positions` | sku_filter | sql_injection | `backend/src/api/routes/v3/positions.py` |
| sql-injection | sqli-positions-position-name | GET | `/api/v3/inventories/33333333-3333-4333-8333-333333333333/aisles/44444444-4444-4444-8444-444444444444/positions` | position_name | sql_injection | `backend/src/api/routes/v3/positions.py` |
| xss-reflection | xss-inventories-search | GET | `/api/v3/inventories/` | search | xss | `backend/src/api/routes/v3/inventories.py` |
| xss-reflection | xss-review-queue-sku | GET | `/api/v3/review-queue/positions` | sku_contains | xss | `backend/src/api/routes/v3/review_queue.py` |
| xss-reflection | xss-position-labels-search | GET | `/api/v3/clients/11111111-1111-4111-8111-111111111111/position-labels` | search | xss | `backend/src/api/routes/v3/client_position_labels.py` |
| template-injection | template-inventories-search | GET | `/api/v3/inventories/` | search | template_injection | `backend/src/api/routes/v3/inventories.py` |
| auth | auth-me-no-token | GET | `/auth/me` |  | auth | `backend/src/auth/routes.py` |
| auth | auth-me-bad-bearer | GET | `/auth/me` |  | auth | `backend/src/auth/routes.py` |
| auth | inventories-no-token | GET | `/api/v3/inventories/` |  | auth | `backend/src/api/routes/v3/inventories.py` |
| auth | clients-no-token | GET | `/api/v3/clients/` |  | auth | `backend/src/api/routes/v3/clients.py` |
| auth | config-no-token | GET | `/api/v3/config/upload-limits` |  | auth | `backend/src/api/routes/v3/config.py` |
| auth | admin-ai-no-token | GET | `/api/v3/admin/ai-config` |  | auth | `backend/src/api/routes/v3/admin_ai_config.py` |
| authorization-idor | idor-client-b-with-admin-a | GET | `/api/v3/clients/22222222-2222-4222-8222-222222222222` |  | idor | `backend/src/api/routes/v3/clients.py` |
| authorization-idor | idor-client-a-with-admin-b | GET | `/api/v3/clients/11111111-1111-4111-8111-111111111111` |  | idor | `backend/src/api/routes/v3/clients.py` |
| authorization-idor | idor-inventory-a-with-admin-b | GET | `/api/v3/inventories/33333333-3333-4333-8333-333333333333` |  | idor | `backend/src/api/routes/v3/inventories.py` |
| authorization-idor | idor-labels-client-a-with-op-b | GET | `/api/v3/clients/11111111-1111-4111-8111-111111111111/position-labels` |  | idor | `backend/src/api/routes/v3/client_position_labels.py` |
| authorization-idor | priv-operator-admin-ai | GET | `/api/v3/admin/ai-config` |  | privilege | `backend/src/api/routes/v3/admin_ai_config.py` |
| multi-tenancy | tenant-review-queue-foreign-inventory | GET | `/api/v3/review-queue/positions` |  | multi_tenancy | `backend/src/api/routes/v3/review_queue.py` |
| multi-tenancy | tenant-observability-foreign-client | GET | `/api/v3/observability/metrics` |  | multi_tenancy | `backend/src/api/routes/v3/observability.py` |
| error-handling | error-inventories-bad-sort | GET | `/api/v3/inventories/` |  | error_handling | `backend/src/api/routes/v3/inventories.py` |
| error-handling | error-review-bad-traceability | GET | `/api/v3/review-queue/positions` |  | error_handling | `backend/src/api/routes/v3/review_queue.py` |

## Counts

- **TOTAL_DAST_CASES:** 35
- **SQLI_CASES:** 6
- **XSS_CASES:** 3
- **AUTH_CASES:** 6
- **IDOR_CASES:** 5
- **TENANT_CASES:** 6
- **PATH_TRAVERSAL_CASES:** 0
- **SSRF_CASES:** 0
- **UPLOAD_CASES:** 0
- **ERROR_VALIDATION_CASES:** 10
- **TEMPLATE_CASES:** 1
- **SMOKE_CASES:** 2
- **estimated_requests:** 102

## Explicitly omitted (not present in code)

- SSRF suites (no user URL → server fetch)
- Open redirect suites (no redirect query params)
- Non-mutating path traversal (downloads are ID-based)
- Upload / DELETE / POST mutating (see mutating example)
- `/public` (does not exist)

