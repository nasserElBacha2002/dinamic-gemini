# 08 — Environment safety matrix

| Class | Allowed tests | Endpoints examples |
|-------|---------------|--------------------|
| LOCAL_SAFE | Auth negative tests, BOLA GET with synthetic IDs, OpenAPI info checks | `/auth/login` lockout probes (rate-limited manually), inventory GET IDOR |
| LOCAL_ISOLATED_ONLY | Uploads, imports, process/reprocess, soft-delete, exports large | assets upload, TXT/ZIP/CSV, `/process` |
| DEV_LOW_RISK | Read-only authenticated GETs with test data | metrics (if key), health |
| MANUAL_ONLY | Production-like LLM cost runs, destructive admin recovery | admin finalization recovery |
| NEVER_ON_SHARED_INSTANCE | Mass delete, mutating DAST, zip bombs, unbounded process | bulk-soft-delete, package confirm storms |

Default: when unsure → **LOCAL_ISOLATED_ONLY** or **NEVER_ON_SHARED_INSTANCE**.
