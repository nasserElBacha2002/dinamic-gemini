# 03 — Authorization matrix

Roles reales (VERIFIED): `platform_admin`, `company_admin` (+ primary `admin` id for AI config). AuthN: JWT Bearer via `get_current_admin` on `/api/v3/inventories` router and peer routers.

Leyenda: ALLOW / DENY / CONDITIONAL / UNKNOWN / NOT_APPLICABLE

| endpoint_id | method | path | anonymous | authenticated_any | platform_admin | company_admin_same | company_admin_other | evidence |
|-------------|--------|------|-----------|-------------------|----------------|--------------------|---------------------|----------|
| EP-0001 | GET | `/api/v3/admin/ai-config` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0002 | GET | `/api/v3/admin/ai-config/composed-prompt` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0003 | POST | `/api/v3/admin/jobs/{job_id}/finalization/recover` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0004 | POST | `/api/v3/admin/storage/cleanup` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0005 | GET | `/api/v3/analytics/aisles` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0006 | GET | `/api/v3/analytics/benchmark/inventories/{inventory_id}/aisles/{aisle_id}/compare` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0007 | GET | `/api/v3/analytics/cost-summary` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0008 | GET | `/api/v3/analytics/inventories` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0009 | GET | `/api/v3/analytics/manual-interventions` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0010 | GET | `/api/v3/analytics/quality` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0011 | GET | `/api/v3/analytics/summary` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0012 | GET | `/api/v3/analytics/trends` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0013 | GET | `/api/v3/clients/` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0014 | POST | `/api/v3/clients/` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0015 | GET | `/api/v3/clients/{client_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0016 | PATCH | `/api/v3/clients/{client_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0017 | GET | `/api/v3/clients/{client_id}/position-labels` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0018 | POST | `/api/v3/clients/{client_id}/position-labels` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0019 | POST | `/api/v3/clients/{client_id}/position-labels/marker-set` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0020 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0021 | PATCH | `/api/v3/clients/{client_id}/position-labels/{label_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0022 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/download` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0023 | POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/invalidate` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0024 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/preview` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0025 | POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/render` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0026 | POST | `/api/v3/clients/{client_id}/product-labels` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0027 | GET | `/api/v3/clients/{client_id}/suppliers` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0028 | POST | `/api/v3/clients/{client_id}/suppliers` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0029 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0030 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0031 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0032 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/active` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0033 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/clone` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0034 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0035 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test-code` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0036 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/versions/{version}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0037 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/{profile_id}/activate` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0038 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0039 | PUT | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles/{label_kind}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0040 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0041 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0042 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/active` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0043 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0044 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}/activate` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0045 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0046 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0047 | DELETE | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0048 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0049 | PUT | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0050 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0051 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/image-display-url` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0052 | GET | `/api/v3/config/extraction-profile-capabilities` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0053 | GET | `/api/v3/config/processing-observability-capabilities` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0054 | GET | `/api/v3/config/upload-limits` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0055 | GET | `/api/v3/inventories/` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0056 | POST | `/api/v3/inventories/` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0057 | POST | `/api/v3/inventories/bulk-soft-delete` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0058 | GET | `/api/v3/inventories/ordered-capture-sessions/{session_id}` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0059 | POST | `/api/v3/inventories/ordered-capture-sessions/{session_id}/seal` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0060 | GET | `/api/v3/inventories/processing-provider-options` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0061 | GET | `/api/v3/inventories/{inventory_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0062 | PATCH | `/api/v3/inventories/{inventory_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0063 | GET | `/api/v3/inventories/{inventory_id}/aisles` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0064 | POST | `/api/v3/inventories/{inventory_id}/aisles` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0065 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0066 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/activate` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0067 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0068 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0069 | DELETE | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0070 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-code-scan` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0071 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0072 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0073 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0074 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{source_asset_id}/manual-result` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0075 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/authoritative-readiness` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0076 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0077 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare-many` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0078 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0079 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0080 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/cancel` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0081 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/clock-offset` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0082 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/close` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0083 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0084 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/materialize` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0085 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/preview-assignment` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0086 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0087 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0088 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/review-signals` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0089 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/run` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0090 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/summary` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0091 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/deactivate` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0092 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0093 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log.txt` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0094 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0095 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/finalize-authoritative` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0096 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0097 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0098 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0099 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0100 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/download` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0101 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/preview` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0102 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/processing` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0103 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0104 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-detail` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0105 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0106 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events/export` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0107 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0108 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0109 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0110 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0111 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0112 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/errors` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0113 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0114 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log.txt` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0115 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log/page` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0116 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/hybrid-report` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0117 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/image-results` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0118 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0119 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry-chain` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0120 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/timeline` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0121 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0122 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/labels/batch-render` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0123 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0124 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0125 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0126 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0127 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0128 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge-results` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0129 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/ordered-capture-sessions` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0130 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-operational-view` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0131 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-sequence` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0132 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-warnings` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0133 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0134 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/by-position` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0135 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0136 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge/preview` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0137 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0138 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/code-scan-evidence` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0139 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0140 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0141 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-reconciliations` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0142 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0143 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing-state` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0144 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing/recover` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0145 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/promote-operational` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0146 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reconcile-preliminary-detections` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0147 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reprocess` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0148 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-capabilities` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0149 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-history` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0150 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0151 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/apply` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0152 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/cancel` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0153 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/diff` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0154 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/items/{asset_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0155 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/rollback` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0156 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0157 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess-capabilities` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0158 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0159 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/adopt` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0160 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/cancel` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0161 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/execute` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0162 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0163 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0164 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0165 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0166 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/cancel` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0167 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/close` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0168 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/compute-groups` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0169 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0170 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/materialize` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0171 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/assign-existing` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0172 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/create-aisle` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0173 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/materialize` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0174 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/preview` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0175 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/items` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0176 | POST | `/api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/confirm` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0177 | POST | `/api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/preview` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0178 | GET | `/api/v3/inventories/{inventory_id}/export` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0179 | GET | `/api/v3/inventories/{inventory_id}/export/package` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0180 | GET | `/api/v3/inventories/{inventory_id}/export/summary` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0181 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-assignments` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0182 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-detections` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0183 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0184 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation/retry` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0185 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-history` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0186 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0187 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override/restore` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0188 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/source-assets/{asset_id}/position-detections` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0189 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/unassigned-results` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0190 | GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/download` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0191 | GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/preview` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0192 | POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/render` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0193 | POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/replace` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0194 | POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/confirm` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0195 | POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/preview` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0196 | GET | `/api/v3/inventories/{inventory_id}/local-csv-imports/{import_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0197 | POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/confirm` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0198 | POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/preview` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0199 | GET | `/api/v3/inventories/{inventory_id}/local-inventory-packages/{package_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0200 | GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0201 | POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0202 | GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0203 | POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0204 | GET | `/api/v3/inventories/{inventory_id}/metrics` | DENY | CONDITIONAL | ALLOW | CONDITIONAL | UNKNOWN | JWT only; tenant filter not verified on this route |
| EP-0205 | GET | `/api/v3/inventories/{inventory_id}/recognition-config` | DENY | CONDITIONAL | ALLOW | ALLOW | DENY | require_inventory_client_scope or capture scope |
| EP-0206 | GET | `/api/v3/observability/metrics` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0207 | GET | `/api/v3/review-queue/positions` | DENY | CONDITIONAL | ALLOW | UNKNOWN | UNKNOWN | authenticated; tenant rules unclear |
| EP-0208 | POST | `/auth/login` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_login |
| EP-0209 | POST | `/auth/logout` | DENY | CONDITIONAL | ALLOW | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE |
| EP-0210 | GET | `/auth/me` | DENY | CONDITIONAL | ALLOW | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE |
| EP-0211 | POST | `/auth/refresh` | DENY | CONDITIONAL | ALLOW | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE |
| EP-0212 | GET | `/docs` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0213 | HEAD | `/docs` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0214 | GET | `/docs/oauth2-redirect` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0215 | HEAD | `/docs/oauth2-redirect` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0216 | GET | `/health` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public |
| EP-0217 | GET | `/metrics` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | conditional_metrics_auth |
| EP-0218 | GET | `/openapi.json` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0219 | HEAD | `/openapi.json` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0220 | GET | `/ready` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public |
| EP-0221 | GET | `/redoc` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
| EP-0222 | HEAD | `/redoc` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | public_docs |
