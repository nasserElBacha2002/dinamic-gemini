# Endpoint inventory — dinamic-gemini

Generated from static AST of `backend/src` FastAPI routes. **No invented paths.**

## Summary

| Metric | Count |
|---|---|
| TOTAL_ENDPOINTS_DISCOVERED | 199 |
| PUBLIC_ENDPOINTS | 3 |
| AUTH_ENDPOINTS | 196 |
| TENANT_SCOPED_ENDPOINTS | 175 |
| UPLOAD_ENDPOINTS | 6 |
| URL_INPUT_ENDPOINTS | 0 |
| MUTATING_ENDPOINTS | 88 |
| DESTRUCTIVE_ENDPOINTS | 2 |
| SEARCH_FILTER_ENDPOINTS | 6 |
| SSRF_CANDIDATES | 0 |
| OPEN_REDIRECT_CANDIDATES | 0 |
| SQL_ENGINE | SQL Server via pyodbc (parameterized). No SQLAlchemy ORM. |
| NO_PUBLIC_ROUTE | True |

Methods: `{'GET': 111, 'POST': 76, 'PATCH': 6, 'DELETE': 2, 'PUT': 4}`

## Auth model

- Scheme: Bearer JWT
- Roles in code: `platform_admin`, `company_admin`, `operator`
- Tenant claim: `client_id`
- Login: `POST /auth/login` with `LoginRequest{username,password}`

## Synthetic fixture IDs (local disposable DB only)

- `client_a`: `11111111-1111-4111-8111-111111111111`
- `client_b`: `22222222-2222-4222-8222-222222222222`
- `inventory_a`: `33333333-3333-4333-8333-333333333333`
- `aisle_a`: `44444444-4444-4444-8444-444444444444`

## OpenAPI

No localhost server responded on 8000/8080/8001/3000/5173 during inventory; OpenAPI comparison deferred to runtime against DAST_BASE_URL/openapi.json

## Endpoints

| Method | Path | Auth | Classes | Source | Handler |
|---|---|---|---|---|---|
| GET | `/api/v3/admin/ai-config` | True | ADMIN_ONLY,AUTH_REQUIRED | `backend/src/api/routes/v3/admin_ai_config.py` | `get_admin_ai_config` |
| GET | `/api/v3/admin/ai-config/composed-prompt` | True | ADMIN_ONLY,AUTH_REQUIRED | `backend/src/api/routes/v3/admin_ai_config.py` | `get_admin_ai_config_composed_prompt` |
| POST | `/api/v3/admin/jobs/{job_id}/finalization/recover` | True | ADMIN_ONLY,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/admin_finalization_recovery.py` | `post_admin_finalization_recover` |
| POST | `/api/v3/admin/storage/cleanup` | True | ADMIN_ONLY,AUTH_REQUIRED,MUTATING | `backend/src/api/routes/v3/admin_storage.py` | `post_admin_storage_cleanup` |
| GET | `/api/v3/analytics/aisles` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_aisles` |
| GET | `/api/v3/analytics/benchmark/inventories/{inventory_id}/aisles/{aisle_id}/compare` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/analytics_api.py` | `analytics_benchmark_compare_aisle_runs` |
| GET | `/api/v3/analytics/cost-summary` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_cost_summary` |
| GET | `/api/v3/analytics/inventories` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_inventories` |
| GET | `/api/v3/analytics/manual-interventions` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_manual_interventions` |
| GET | `/api/v3/analytics/quality` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_quality` |
| GET | `/api/v3/analytics/summary` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_summary` |
| GET | `/api/v3/analytics/trends` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/analytics_api.py` | `analytics_trends` |
| GET | `/api/v3/clients/` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/clients.py` | `list_clients` |
| POST | `/api/v3/clients/` | True | AUTH_REQUIRED,MUTATING | `backend/src/api/routes/v3/clients.py` | `create_client` |
| GET | `/api/v3/clients/{client_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_client` |
| PATCH | `/api/v3/clients/{client_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `update_client` |
| GET | `/api/v3/clients/{client_id}/position-labels` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,SEARCH_FILTER,TENANT_SENSITIVE | `backend/src/api/routes/v3/client_position_labels.py` | `list_client_position_labels` |
| POST | `/api/v3/clients/{client_id}/position-labels` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/client_position_labels.py` | `create_client_position_label` |
| GET | `/api/v3/clients/{client_id}/position-labels/{label_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/client_position_labels.py` | `get_client_position_label` |
| PATCH | `/api/v3/clients/{client_id}/position-labels/{label_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/client_position_labels.py` | `update_client_position_label` |
| GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/download` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/client_position_labels.py` | `download_client_position_label` |
| POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/invalidate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/client_position_labels.py` | `invalidate_client_position_label` |
| GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/client_position_labels.py` | `preview_client_position_label` |
| POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/render` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/client_position_labels.py` | `render_client_position_label` |
| GET | `/api/v3/clients/{client_id}/suppliers` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `list_client_suppliers` |
| POST | `/api/v3/clients/{client_id}/suppliers` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `create_client_supplier` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_client_supplier` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `list_supplier_extraction_profiles` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `create_supplier_extraction_profile` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/active` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_active_supplier_extraction_profile` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/clone` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `clone_supplier_extraction_profile` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `test_supplier_extraction_profile` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/versions/{version}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_supplier_extraction_profile_by_version` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/{profile_id}/activate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `activate_supplier_extraction_profile` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `list_supplier_prompt_configs` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `create_supplier_prompt_config` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/active` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_active_supplier_prompt_config` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_supplier_prompt_config` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}/activate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `activate_supplier_prompt_config` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `list_supplier_reference_images` |
| POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_UPLOAD,MUTATING | `backend/src/api/routes/v3/clients.py` | `upload_supplier_reference_images` |
| DELETE | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,DESTRUCTIVE,MUTATING | `backend/src/api/routes/v3/clients.py` | `delete_supplier_reference_image` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `list_supplier_reference_annotations` |
| PUT | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/clients.py` | `replace_supplier_reference_annotations` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/clients.py` | `get_supplier_reference_image_file` |
| GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/image-display-url` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/clients.py` | `get_supplier_reference_image_display_url` |
| GET | `/api/v3/config/extraction-profile-capabilities` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/config.py` | `get_extraction_profile_capabilities` |
| GET | `/api/v3/config/processing-observability-capabilities` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/config.py` | `get_processing_observability_capabilities` |
| GET | `/api/v3/config/upload-limits` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/config.py` | `get_upload_limits` |
| GET | `/api/v3/inventories/` | True | AUTH_REQUIRED,SEARCH_FILTER | `backend/src/api/routes/v3/inventories.py` | `list_inventories` |
| POST | `/api/v3/inventories/` | True | AUTH_REQUIRED,MUTATING | `backend/src/api/routes/v3/inventories.py` | `create_inventory` |
| GET | `/api/v3/inventories/ordered-capture-sessions/{session_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,TENANT_SENSITIVE | `backend/src/api/routes/v3/ordered_capture.py` | `get_ordered_capture_session` |
| POST | `/api/v3/inventories/ordered-capture-sessions/{session_id}/seal` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,TENANT_SENSITIVE | `backend/src/api/routes/v3/ordered_capture.py` | `seal_ordered_capture_session` |
| GET | `/api/v3/inventories/processing-provider-options` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/inventories.py` | `list_processing_provider_options` |
| GET | `/api/v3/inventories/{inventory_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/inventories.py` | `get_inventory` |
| PATCH | `/api/v3/inventories/{inventory_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/inventories.py` | `update_inventory` |
| GET | `/api/v3/inventories/{inventory_id}/aisles` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `list_aisles` |
| POST | `/api/v3/inventories/{inventory_id}/aisles` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `create_aisle` |
| PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `update_aisle_code` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/activate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `activate_aisle` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/assets.py` | `list_aisle_assets` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_UPLOAD,MUTATING | `backend/src/api/routes/v3/assets.py` | `upload_aisle_assets` |
| DELETE | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,DESTRUCTIVE,MUTATING | `backend/src/api/routes/v3/assets.py` | `delete_aisle_source_asset` |
| PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-code-scan` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/authoritative_local_code_scan.py` | `put_authoritative_local_code_scan` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/authoritative_aisle_finalization.py` | `post_authoritative_exclusion` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/assets.py` | `get_aisle_asset_file` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/assets.py` | `get_aisle_asset_image_display_url` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{source_asset_id}/manual-result` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/image_results.py` | `create_manual_image_result` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/authoritative-readiness` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/authoritative_aisle_finalization.py` | `get_authoritative_aisle_readiness` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `compare_aisle_benchmark_runs` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare-many` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `compare_many_aisle_benchmark_runs` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `export_aisle_benchmark` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `create_capture_session` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/cancel` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `cancel_capture_session` |
| PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/clock-offset` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `patch_capture_session_clock_offset` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/close` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `close_capture_session` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_UPLOAD,MUTATING | `backend/src/api/routes/v3/capture_sessions.py` | `upload_capture_session_staging_items` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/materialize` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `post_capture_session_materialize` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/preview-assignment` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,MUTATING | `backend/src/api/routes/v3/capture_sessions.py` | `post_capture_session_preview_assignment` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/code_scans.py` | `list_aisle_code_scans` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/code_scans.py` | `export_aisle_code_scans` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/review-signals` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/code_scans.py` | `get_aisle_code_scan_review_signals` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/run` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/code_scans.py` | `run_aisle_code_scan` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/summary` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/code_scans.py` | `summarize_aisle_code_scans` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/deactivate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `deactivate_aisle` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_aggregated_execution_log` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log.txt` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_aggregated_execution_log_txt` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `export_aisle_results_csv` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/finalize-authoritative` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/authoritative_aisle_finalization.py` | `post_finalize_authoritative_aisle` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `list_aisle_jobs` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_job_detail` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `list_job_artifacts` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_artifact_metadata` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/download` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `download_job_artifact` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `preview_job_artifact` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/processing` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/processing_observability.py` | `list_asset_processing` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/processing_observability.py` | `invalidate_asset_result` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-detail` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/processing_observability.py` | `get_asset_processing_detail` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/processing_observability.py` | `list_processing_events` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events/export` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/processing_observability.py` | `export_processing_events` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/processing_observability.py` | `reprocess_asset` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/processing_observability.py` | `retry_asset_persistence` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/processing_observability.py` | `send_asset_to_external` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_run_auditability` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `cancel_aisle_job` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/errors` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_errors` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_execution_log` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log.txt` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_execution_log_txt` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log/page` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_execution_log_page` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/hybrid-report` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_hybrid_report` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/image-results` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/image_results.py` | `list_job_image_results` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `retry_aisle_job` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry-chain` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_retry_chain` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/timeline` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_timeline` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_job_traceability` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/labels/batch-render` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `batch_render_aisle_location_labels` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,SEARCH_FILTER | `backend/src/api/routes/v3/aisle_locations.py` | `list_aisle_locations` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `create_aisle_location` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_locations.py` | `get_aisle_location` |
| PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `update_aisle_location` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `run_aisle_merge` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge-results` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_merge_results` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/ordered-capture-sessions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/ordered_capture.py` | `create_ordered_capture_session` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-operational-view` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/positioning_operational.py` | `get_positioning_operational_view` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-sequence` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/positioning_operational.py` | `get_positioning_sequence` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-warnings` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/positioning_operational.py` | `get_positioning_warnings` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,SEARCH_FILTER | `backend/src/api/routes/v3/positions.py` | `list_aisle_positions` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/by-position` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/positions.py` | `list_aisle_positions_by_position` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,SEARCH_FILTER | `backend/src/api/routes/v3/positions.py` | `get_position_detail` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/code-scan-evidence` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/positions.py` | `get_position_code_scan_evidence` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/reviews.py` | `submit_review_action` |
| PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/preliminary_detections.py` | `upsert_preliminary_detection` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-reconciliations` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/preliminary_reconciliations.py` | `list_preliminary_reconciliations` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `start_aisle_processing` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing-state` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_processing_state` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing/recover` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `recover_aisle_processing` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/promote-operational` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisles.py` | `promote_aisle_operational_job` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reconcile-preliminary-detections` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/preliminary_reconciliations.py` | `reconcile_preliminary_detections` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reprocess` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/positioning_operational.py` | `reprocess_aisle_positioning` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-capabilities` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_revisions.py` | `get_revision_capabilities` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-history` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_revisions.py` | `list_revision_history` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_revisions.py` | `create_revision` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/apply` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_revisions.py` | `apply_revision` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/cancel` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_revisions.py` | `cancel_revision` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/diff` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_revisions.py` | `get_revision_diff` |
| PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/items/{asset_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_revisions.py` | `update_revision_item` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/rollback` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_revisions.py` | `rollback_aisle` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/server_reprocess.py` | `post_server_reprocess` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess-capabilities` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/server_reprocess.py` | `get_server_reprocess_capabilities` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/server_reprocess.py` | `get_server_reprocess` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/adopt` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/server_reprocess.py` | `post_adopt_server_reprocess` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/cancel` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/server_reprocess.py` | `post_cancel_server_reprocess` |
| POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/execute` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/server_reprocess.py` | `post_execute_server_reprocess` |
| GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisles.py` | `get_aisle_status` |
| GET | `/api/v3/inventories/{inventory_id}/capture-sessions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/capture_sessions.py` | `list_capture_sessions` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `create_inventory_capture_session` |
| GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/capture_sessions.py` | `get_capture_session_detail` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/cancel` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `cancel_capture_session_inventory_scope` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/close` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `close_capture_session_inventory_scope` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/compute-groups` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `compute_capture_session_groups_inventory_scope` |
| GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/capture_sessions.py` | `list_capture_session_groups_inventory_scope` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/materialize` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `post_materialize_all_assigned_capture_session_groups` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/assign-existing` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `assign_capture_session_group_to_existing_aisle_inventory_scope` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/create-aisle` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `create_aisle_and_assign_capture_session_group_inventory_scope` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/materialize` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/capture_sessions.py` | `post_materialize_capture_session_group` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,MUTATING | `backend/src/api/routes/v3/capture_sessions.py` | `post_materialized_capture_session_group_preview` |
| POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/items` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_UPLOAD,MUTATING | `backend/src/api/routes/v3/capture_sessions.py` | `upload_capture_session_staging_items_inventory_scope` |
| GET | `/api/v3/inventories/{inventory_id}/export` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/inventories.py` | `export_inventory_results` |
| GET | `/api/v3/inventories/{inventory_id}/export/package` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/inventories.py` | `export_inventory_package_zip` |
| GET | `/api/v3/inventories/{inventory_id}/export/summary` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/inventories.py` | `export_inventory_summary_csv` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-assignments` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_reconciliation.py` | `list_job_position_assignments` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-detections` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_label_detections.py` | `list_job_position_detections` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_reconciliation.py` | `get_job_position_reconciliation` |
| POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation/retry` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/position_reconciliation.py` | `retry_job_position_reconciliation` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-history` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_overrides.py` | `get_position_history` |
| POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/position_overrides.py` | `create_position_override` |
| POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override/restore` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/position_overrides.py` | `restore_automatic_position` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/source-assets/{asset_id}/position-detections` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_label_detections.py` | `list_asset_position_detections` |
| GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/unassigned-results` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/position_reconciliation.py` | `list_job_unassigned_results` |
| GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/download` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `download_aisle_location_label` |
| GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `preview_aisle_location_label` |
| POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/render` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `render_aisle_location_label` |
| POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/replace` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `replace_aisle_location_label` |
| POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/confirm` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/local_csv_imports.py` | `confirm_local_csv_import` |
| POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,FILE_UPLOAD | `backend/src/api/routes/v3/local_csv_imports.py` | `preview_local_csv_import` |
| GET | `/api/v3/inventories/{inventory_id}/local-csv-imports/{import_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/local_csv_imports.py` | `get_local_csv_import` |
| POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/confirm` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/local_inventory_packages.py` | `confirm_local_inventory_package` |
| POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/preview` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,FILE_DOWNLOAD,FILE_UPLOAD | `backend/src/api/routes/v3/local_inventory_packages.py` | `preview_local_inventory_package` |
| GET | `/api/v3/inventories/{inventory_id}/local-inventory-packages/{package_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/local_inventory_packages.py` | `get_local_inventory_package` |
| GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_locations.py` | `list_aisle_location_labels` |
| POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `issue_aisle_location_label` |
| GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/aisle_locations.py` | `get_aisle_location_label` |
| POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,MUTATING,RESOURCE_BY_ID | `backend/src/api/routes/v3/aisle_locations.py` | `invalidate_aisle_location_label` |
| GET | `/api/v3/inventories/{inventory_id}/metrics` | True | AUTHORIZATION_SENSITIVE,AUTH_REQUIRED,RESOURCE_BY_ID,TENANT_SENSITIVE | `backend/src/api/routes/v3/inventories.py` | `get_inventory_metrics` |
| GET | `/api/v3/observability/metrics` | True | AUTH_REQUIRED | `backend/src/api/routes/v3/observability.py` | `get_observability_metrics` |
| GET | `/api/v3/review-queue/positions` | True | AUTH_REQUIRED,SEARCH_FILTER | `backend/src/api/routes/v3/review_queue.py` | `list_review_queue_positions` |
| GET | `/health` | False | HEALTH | `backend/src/api/server.py` | `health` |
| GET | `/metrics` | False | INTERNAL | `backend/src/api/server.py` | `metrics` |
| GET | `/ready` | False | HEALTH | `backend/src/api/server.py` | `ready` |
