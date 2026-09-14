# 01 — Endpoint inventory (human)
Fuente: registro FastAPI. Detalle machine-readable en `endpoint-inventory.json` / `02-endpoint-inventory.csv`.

## Module: `admin` (4)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0001 | GET | `/api/v3/admin/ai-config` | Y | AUTHORIZATION_UNKNOWN | HIGH | `get_admin_ai_config` | backend/src/api/routes/v3/admin_ai_config.py:27 |
| EP-0002 | GET | `/api/v3/admin/ai-config/composed-prompt` | Y | AUTHORIZATION_UNKNOWN | HIGH | `get_admin_ai_config_composed_prompt` | backend/src/api/routes/v3/admin_ai_config.py:34 |
| EP-0003 | POST | `/api/v3/admin/jobs/{job_id}/finalization/recover` | Y | POTENTIAL_BOLA | HIGH | `post_admin_finalization_recover` | backend/src/api/routes/v3/admin_finalization_recovery.py:61 |
| EP-0004 | POST | `/api/v3/admin/storage/cleanup` | Y | AUTHORIZATION_UNKNOWN | HIGH | `post_admin_storage_cleanup` | backend/src/api/routes/v3/admin_storage.py:34 |

## Module: `aisle_locations` (4)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0123 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | Y | CONTROL_VERIFIED | LOW | `list_aisle_locations` | backend/src/api/routes/v3/aisle_locations.py:120 |
| EP-0124 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations` | Y | CONTROL_VERIFIED | MEDIUM | `create_aisle_location` | backend/src/api/routes/v3/aisle_locations.py:89 |
| EP-0125 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | Y | CONTROL_VERIFIED | LOW | `get_aisle_location` | backend/src/api/routes/v3/aisle_locations.py:160 |
| EP-0126 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}` | Y | CONTROL_VERIFIED | MEDIUM | `update_aisle_location` | backend/src/api/routes/v3/aisle_locations.py:190 |

## Module: `aisle_revisions` (5)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0150 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions` | Y | POTENTIAL_BOLA | HIGH | `create_revision` | backend/src/api/routes/v3/aisle_revisions.py:180 |
| EP-0151 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/apply` | Y | POTENTIAL_BOLA | HIGH | `apply_revision` | backend/src/api/routes/v3/aisle_revisions.py:242 |
| EP-0152 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/cancel` | Y | POTENTIAL_BOLA | HIGH | `cancel_revision` | backend/src/api/routes/v3/aisle_revisions.py:340 |
| EP-0153 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/diff` | Y | POTENTIAL_BOLA | HIGH | `get_revision_diff` | backend/src/api/routes/v3/aisle_revisions.py:270 |
| EP-0154 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/items/{asset_id}` | Y | POTENTIAL_BOLA | HIGH | `update_revision_item` | backend/src/api/routes/v3/aisle_revisions.py:208 |

## Module: `aisles` (30)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0063 | GET | `/api/v3/inventories/{inventory_id}/aisles` | Y | POTENTIAL_BOLA | HIGH | `list_aisles` | backend/src/api/routes/v3/aisles.py:506 |
| EP-0064 | POST | `/api/v3/inventories/{inventory_id}/aisles` | Y | POTENTIAL_BOLA | HIGH | `create_aisle` | backend/src/api/routes/v3/aisles.py:380 |
| EP-0065 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}` | Y | POTENTIAL_BOLA | HIGH | `update_aisle_code` | backend/src/api/routes/v3/aisles.py:411 |
| EP-0066 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/activate` | Y | POTENTIAL_BOLA | HIGH | `activate_aisle` | backend/src/api/routes/v3/aisles.py:483 |
| EP-0076 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare` | Y | POTENTIAL_BOLA | HIGH | `compare_aisle_benchmark_runs` | backend/src/api/routes/v3/aisles.py:1999 |
| EP-0077 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/compare-many` | Y | POTENTIAL_BOLA | HIGH | `compare_many_aisle_benchmark_runs` | backend/src/api/routes/v3/aisles.py:2034 |
| EP-0078 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export` | Y | POTENTIAL_BOLA | CRITICAL | `export_aisle_benchmark` | backend/src/api/routes/v3/aisles.py:2093 |
| EP-0091 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/deactivate` | Y | POTENTIAL_BOLA | HIGH | `deactivate_aisle` | backend/src/api/routes/v3/aisles.py:460 |
| EP-0092 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_aggregated_execution_log` | backend/src/api/routes/v3/aisles.py:764 |
| EP-0093 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/execution-log.txt` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_aggregated_execution_log_txt` | backend/src/api/routes/v3/aisles.py:794 |
| EP-0094 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` | Y | POTENTIAL_BOLA | CRITICAL | `export_aisle_results_csv` | backend/src/api/routes/v3/aisles.py:1937 |
| EP-0122 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/labels/batch-render` | Y | CONTROL_VERIFIED | MEDIUM | `batch_render_aisle_location_labels` | backend/src/api/routes/v3/aisle_locations.py:526 |
| EP-0127 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge` | Y | POTENTIAL_BOLA | HIGH | `run_aisle_merge` | backend/src/api/routes/v3/aisles.py:1850 |
| EP-0128 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/merge-results` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_merge_results` | backend/src/api/routes/v3/aisles.py:1892 |
| EP-0129 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/ordered-capture-sessions` | Y | CONTROL_VERIFIED | MEDIUM | `create_ordered_capture_session` | backend/src/api/routes/v3/ordered_capture.py:39 |
| EP-0130 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-operational-view` | Y | POTENTIAL_BOLA | HIGH | `get_positioning_operational_view` | backend/src/api/routes/v3/positioning_operational.py:45 |
| EP-0131 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-sequence` | Y | POTENTIAL_BOLA | HIGH | `get_positioning_sequence` | backend/src/api/routes/v3/positioning_operational.py:73 |
| EP-0132 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-warnings` | Y | POTENTIAL_BOLA | HIGH | `get_positioning_warnings` | backend/src/api/routes/v3/positioning_operational.py:111 |
| EP-0145 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/promote-operational` | Y | POTENTIAL_BOLA | HIGH | `promote_aisle_operational_job` | backend/src/api/routes/v3/aisles.py:2066 |
| EP-0146 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reconcile-preliminary-detections` | Y | POTENTIAL_BOLA | HIGH | `reconcile_preliminary_detections` | backend/src/api/routes/v3/preliminary_reconciliations.py:69 |
| EP-0148 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-capabilities` | Y | POTENTIAL_BOLA | HIGH | `get_revision_capabilities` | backend/src/api/routes/v3/aisle_revisions.py:141 |
| EP-0149 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-history` | Y | POTENTIAL_BOLA | HIGH | `list_revision_history` | backend/src/api/routes/v3/aisle_revisions.py:305 |
| EP-0155 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/rollback` | Y | POTENTIAL_BOLA | HIGH | `rollback_aisle` | backend/src/api/routes/v3/aisle_revisions.py:360 |
| EP-0156 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess` | Y | POTENTIAL_BOLA | HIGH | `post_server_reprocess` | backend/src/api/routes/v3/server_reprocess.py:124 |
| EP-0157 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess-capabilities` | Y | POTENTIAL_BOLA | HIGH | `get_server_reprocess_capabilities` | backend/src/api/routes/v3/server_reprocess.py:288 |
| EP-0158 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}` | Y | POTENTIAL_BOLA | HIGH | `get_server_reprocess` | backend/src/api/routes/v3/server_reprocess.py:175 |
| EP-0159 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/adopt` | Y | POTENTIAL_BOLA | HIGH | `post_adopt_server_reprocess` | backend/src/api/routes/v3/server_reprocess.py:353 |
| EP-0160 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/cancel` | Y | POTENTIAL_BOLA | HIGH | `post_cancel_server_reprocess` | backend/src/api/routes/v3/server_reprocess.py:328 |
| EP-0161 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/execute` | Y | POTENTIAL_BOLA | HIGH | `post_execute_server_reprocess` | backend/src/api/routes/v3/server_reprocess.py:242 |
| EP-0162 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_status` | backend/src/api/routes/v3/aisles.py:630 |

## Module: `analytics` (8)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0005 | GET | `/api/v3/analytics/aisles` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_aisles` | backend/src/api/routes/v3/analytics_api.py:379 |
| EP-0006 | GET | `/api/v3/analytics/benchmark/inventories/{inventory_id}/aisles/{aisle_id}/compare` | Y | POTENTIAL_BOLA | HIGH | `analytics_benchmark_compare_aisle_runs` | backend/src/api/routes/v3/analytics_api.py:469 |
| EP-0007 | GET | `/api/v3/analytics/cost-summary` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_cost_summary` | backend/src/api/routes/v3/analytics_api.py:152 |
| EP-0008 | GET | `/api/v3/analytics/inventories` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_inventories` | backend/src/api/routes/v3/analytics_api.py:340 |
| EP-0009 | GET | `/api/v3/analytics/manual-interventions` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_manual_interventions` | backend/src/api/routes/v3/analytics_api.py:435 |
| EP-0010 | GET | `/api/v3/analytics/quality` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_quality` | backend/src/api/routes/v3/analytics_api.py:412 |
| EP-0011 | GET | `/api/v3/analytics/summary` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_summary` | backend/src/api/routes/v3/analytics_api.py:263 |
| EP-0012 | GET | `/api/v3/analytics/trends` | Y | AUTHORIZATION_UNKNOWN | LOW | `analytics_trends` | backend/src/api/routes/v3/analytics_api.py:311 |

## Module: `assets` (16)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0067 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | Y | CONTROL_VERIFIED | LOW | `list_aisle_assets` | backend/src/api/routes/v3/assets.py:186 |
| EP-0068 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | Y | CONTROL_VERIFIED | HIGH | `upload_aisle_assets` | backend/src/api/routes/v3/assets.py:113 |
| EP-0069 | DELETE | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}` | Y | CONTROL_VERIFIED | HIGH | `delete_aisle_source_asset` | backend/src/api/routes/v3/assets.py:389 |
| EP-0070 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-code-scan` | Y | POTENTIAL_BOLA | HIGH | `put_authoritative_local_code_scan` | backend/src/api/routes/v3/authoritative_local_code_scan.py:33 |
| EP-0071 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion` | Y | POTENTIAL_BOLA | HIGH | `post_authoritative_exclusion` | backend/src/api/routes/v3/authoritative_aisle_finalization.py:102 |
| EP-0072 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file` | Y | CONTROL_VERIFIED | LOW | `get_aisle_asset_file` | backend/src/api/routes/v3/assets.py:202 |
| EP-0073 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url` | Y | CONTROL_VERIFIED | LOW | `get_aisle_asset_image_display_url` | backend/src/api/routes/v3/assets.py:302 |
| EP-0074 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{source_asset_id}/manual-result` | Y | POTENTIAL_BOLA | HIGH | `create_manual_image_result` | backend/src/api/routes/v3/image_results.py:158 |
| EP-0102 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/processing` | Y | POTENTIAL_BOLA | HIGH | `list_asset_processing` | backend/src/api/routes/v3/processing_observability.py:116 |
| EP-0103 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result` | Y | POTENTIAL_BOLA | HIGH | `invalidate_asset_result` | backend/src/api/routes/v3/processing_observability.py:310 |
| EP-0104 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-detail` | Y | POTENTIAL_BOLA | HIGH | `get_asset_processing_detail` | backend/src/api/routes/v3/processing_observability.py:170 |
| EP-0105 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events` | Y | POTENTIAL_BOLA | HIGH | `list_processing_events` | backend/src/api/routes/v3/processing_observability.py:219 |
| EP-0106 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events/export` | Y | POTENTIAL_BOLA | HIGH | `export_processing_events` | backend/src/api/routes/v3/processing_observability.py:413 |
| EP-0107 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess` | Y | POTENTIAL_BOLA | HIGH | `reprocess_asset` | backend/src/api/routes/v3/processing_observability.py:273 |
| EP-0108 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence` | Y | POTENTIAL_BOLA | HIGH | `retry_asset_persistence` | backend/src/api/routes/v3/processing_observability.py:343 |
| EP-0109 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external` | Y | POTENTIAL_BOLA | HIGH | `send_asset_to_external` | backend/src/api/routes/v3/processing_observability.py:378 |

## Module: `auth` (4)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0208 | POST | `/auth/login` | N | NOT_APPLICABLE | CRITICAL | `login` | backend/src/auth/routes.py:32 |
| EP-0209 | POST | `/auth/logout` | Y | NOT_APPLICABLE | HIGH | `logout` | backend/src/auth/routes.py:97 |
| EP-0210 | GET | `/auth/me` | Y | NOT_APPLICABLE | HIGH | `get_me` | backend/src/auth/routes.py:59 |
| EP-0211 | POST | `/auth/refresh` | Y | NOT_APPLICABLE | HIGH | `refresh_tokens` | backend/src/auth/routes.py:73 |

## Module: `authoritative_local` (2)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0075 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/authoritative-readiness` | Y | POTENTIAL_BOLA | HIGH | `get_authoritative_aisle_readiness` | backend/src/api/routes/v3/authoritative_aisle_finalization.py:56 |
| EP-0095 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/finalize-authoritative` | Y | POTENTIAL_BOLA | HIGH | `post_finalize_authoritative_aisle` | backend/src/api/routes/v3/authoritative_aisle_finalization.py:169 |

## Module: `capture` (7)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0079 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions` | Y | POTENTIAL_BOLA | HIGH | `create_capture_session` | backend/src/api/routes/v3/capture_sessions.py:177 |
| EP-0080 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/cancel` | Y | POTENTIAL_BOLA | HIGH | `cancel_capture_session` | backend/src/api/routes/v3/capture_sessions.py:253 |
| EP-0081 | PATCH | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/clock-offset` | Y | POTENTIAL_BOLA | HIGH | `patch_capture_session_clock_offset` | backend/src/api/routes/v3/capture_sessions.py:314 |
| EP-0082 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/close` | Y | POTENTIAL_BOLA | HIGH | `close_capture_session` | backend/src/api/routes/v3/capture_sessions.py:214 |
| EP-0083 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items` | Y | CONTROL_VERIFIED | MEDIUM | `upload_capture_session_staging_items` | backend/src/api/routes/v3/capture_sessions.py:622 |
| EP-0084 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/materialize` | Y | POTENTIAL_BOLA | HIGH | `post_capture_session_materialize` | backend/src/api/routes/v3/capture_sessions.py:364 |
| EP-0085 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/preview-assignment` | Y | POTENTIAL_BOLA | HIGH | `post_capture_session_preview_assignment` | backend/src/api/routes/v3/capture_sessions.py:342 |

## Module: `clients` (39)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0013 | GET | `/api/v3/clients/` | Y | POTENTIAL_BOLA | CRITICAL | `list_clients` | backend/src/api/routes/v3/clients.py:371 |
| EP-0014 | POST | `/api/v3/clients/` | Y | POTENTIAL_BOLA | CRITICAL | `create_client` | backend/src/api/routes/v3/clients.py:357 |
| EP-0015 | GET | `/api/v3/clients/{client_id}` | Y | POTENTIAL_BOLA | CRITICAL | `get_client` | backend/src/api/routes/v3/clients.py:391 |
| EP-0016 | PATCH | `/api/v3/clients/{client_id}` | Y | POTENTIAL_BOLA | CRITICAL | `update_client` | backend/src/api/routes/v3/clients.py:404 |
| EP-0017 | GET | `/api/v3/clients/{client_id}/position-labels` | Y | POTENTIAL_BOLA | HIGH | `list_client_position_labels` | backend/src/api/routes/v3/client_position_labels.py:174 |
| EP-0018 | POST | `/api/v3/clients/{client_id}/position-labels` | Y | POTENTIAL_BOLA | HIGH | `create_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:212 |
| EP-0019 | POST | `/api/v3/clients/{client_id}/position-labels/marker-set` | Y | POTENTIAL_BOLA | HIGH | `create_client_position_marker_set` | backend/src/api/routes/v3/client_position_labels.py:248 |
| EP-0020 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}` | Y | POTENTIAL_BOLA | HIGH | `get_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:284 |
| EP-0021 | PATCH | `/api/v3/clients/{client_id}/position-labels/{label_id}` | Y | POTENTIAL_BOLA | HIGH | `update_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:307 |
| EP-0022 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/download` | Y | POTENTIAL_BOLA | HIGH | `download_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:464 |
| EP-0023 | POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/invalidate` | Y | POTENTIAL_BOLA | HIGH | `invalidate_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:337 |
| EP-0024 | GET | `/api/v3/clients/{client_id}/position-labels/{label_id}/preview` | Y | POTENTIAL_BOLA | HIGH | `preview_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:442 |
| EP-0025 | POST | `/api/v3/clients/{client_id}/position-labels/{label_id}/render` | Y | POTENTIAL_BOLA | HIGH | `render_client_position_label` | backend/src/api/routes/v3/client_position_labels.py:366 |
| EP-0026 | POST | `/api/v3/clients/{client_id}/product-labels` | Y | POTENTIAL_BOLA | HIGH | `issue_product_labels` | backend/src/api/routes/v3/client_product_labels.py:49 |
| EP-0027 | GET | `/api/v3/clients/{client_id}/suppliers` | Y | POTENTIAL_BOLA | HIGH | `list_client_suppliers` | backend/src/api/routes/v3/clients.py:452 |
| EP-0028 | POST | `/api/v3/clients/{client_id}/suppliers` | Y | POTENTIAL_BOLA | HIGH | `create_client_supplier` | backend/src/api/routes/v3/clients.py:428 |
| EP-0029 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}` | Y | POTENTIAL_BOLA | HIGH | `get_client_supplier` | backend/src/api/routes/v3/clients.py:477 |
| EP-0030 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | Y | POTENTIAL_BOLA | HIGH | `list_supplier_extraction_profiles` | backend/src/api/routes/v3/clients.py:806 |
| EP-0031 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles` | Y | POTENTIAL_BOLA | HIGH | `create_supplier_extraction_profile` | backend/src/api/routes/v3/clients.py:831 |
| EP-0032 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/active` | Y | POTENTIAL_BOLA | HIGH | `get_active_supplier_extraction_profile` | backend/src/api/routes/v3/clients.py:869 |
| EP-0033 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/clone` | Y | POTENTIAL_BOLA | HIGH | `clone_supplier_extraction_profile` | backend/src/api/routes/v3/clients.py:922 |
| EP-0034 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test` | Y | POTENTIAL_BOLA | HIGH | `test_supplier_extraction_profile` | backend/src/api/routes/v3/clients.py:949 |
| EP-0035 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test-code` | Y | POTENTIAL_BOLA | HIGH | `test_supplier_label_recognition_code` | backend/src/api/routes/v3/clients.py:993 |
| EP-0036 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/versions/{version}` | Y | POTENTIAL_BOLA | HIGH | `get_supplier_extraction_profile_by_version` | backend/src/api/routes/v3/clients.py:896 |
| EP-0037 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/{profile_id}/activate` | Y | POTENTIAL_BOLA | HIGH | `activate_supplier_extraction_profile` | backend/src/api/routes/v3/clients.py:1036 |
| EP-0038 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles` | Y | POTENTIAL_BOLA | HIGH | `list_client_supplier_label_profiles` | backend/src/api/routes/v3/clients.py:1130 |
| EP-0039 | PUT | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles/{label_kind}` | Y | POTENTIAL_BOLA | HIGH | `upsert_client_supplier_label_profile` | backend/src/api/routes/v3/clients.py:1159 |
| EP-0040 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | Y | POTENTIAL_BOLA | HIGH | `list_supplier_prompt_configs` | backend/src/api/routes/v3/clients.py:668 |
| EP-0041 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs` | Y | POTENTIAL_BOLA | HIGH | `create_supplier_prompt_config` | backend/src/api/routes/v3/clients.py:698 |
| EP-0042 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/active` | Y | POTENTIAL_BOLA | HIGH | `get_active_supplier_prompt_config` | backend/src/api/routes/v3/clients.py:728 |
| EP-0043 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}` | Y | POTENTIAL_BOLA | HIGH | `get_supplier_prompt_config` | backend/src/api/routes/v3/clients.py:760 |
| EP-0044 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}/activate` | Y | POTENTIAL_BOLA | HIGH | `activate_supplier_prompt_config` | backend/src/api/routes/v3/clients.py:782 |
| EP-0045 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | Y | POTENTIAL_BOLA | HIGH | `list_supplier_reference_images` | backend/src/api/routes/v3/clients.py:491 |
| EP-0046 | POST | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images` | Y | POTENTIAL_BOLA | HIGH | `upload_supplier_reference_images` | backend/src/api/routes/v3/clients.py:512 |
| EP-0047 | DELETE | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}` | Y | POTENTIAL_BOLA | HIGH | `delete_supplier_reference_image` | backend/src/api/routes/v3/clients.py:561 |
| EP-0048 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | Y | POTENTIAL_BOLA | HIGH | `list_supplier_reference_annotations` | backend/src/api/routes/v3/clients.py:1071 |
| EP-0049 | PUT | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations` | Y | POTENTIAL_BOLA | HIGH | `replace_supplier_reference_annotations` | backend/src/api/routes/v3/clients.py:1099 |
| EP-0050 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file` | Y | POTENTIAL_BOLA | HIGH | `get_supplier_reference_image_file` | backend/src/api/routes/v3/clients.py:635 |
| EP-0051 | GET | `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/image-display-url` | Y | POTENTIAL_BOLA | HIGH | `get_supplier_reference_image_display_url` | backend/src/api/routes/v3/clients.py:599 |

## Module: `code_scans` (5)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0086 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans` | Y | POTENTIAL_BOLA | HIGH | `list_aisle_code_scans` | backend/src/api/routes/v3/code_scans.py:145 |
| EP-0087 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export` | Y | POTENTIAL_BOLA | CRITICAL | `export_aisle_code_scans` | backend/src/api/routes/v3/code_scans.py:255 |
| EP-0088 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/review-signals` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_code_scan_review_signals` | backend/src/api/routes/v3/code_scans.py:205 |
| EP-0089 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/run` | Y | POTENTIAL_BOLA | HIGH | `run_aisle_code_scan` | backend/src/api/routes/v3/code_scans.py:97 |
| EP-0090 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/summary` | Y | POTENTIAL_BOLA | HIGH | `summarize_aisle_code_scans` | backend/src/api/routes/v3/code_scans.py:168 |

## Module: `config` (3)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0052 | GET | `/api/v3/config/extraction-profile-capabilities` | Y | AUTHORIZATION_UNKNOWN | LOW | `get_extraction_profile_capabilities` | backend/src/api/routes/v3/config.py:49 |
| EP-0053 | GET | `/api/v3/config/processing-observability-capabilities` | Y | AUTHORIZATION_UNKNOWN | HIGH | `get_processing_observability_capabilities` | backend/src/api/routes/v3/config.py:77 |
| EP-0054 | GET | `/api/v3/config/upload-limits` | Y | AUTHORIZATION_UNKNOWN | HIGH | `get_upload_limits` | backend/src/api/routes/v3/config.py:27 |

## Module: `dinamic_scanner_txt` (2)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0176 | POST | `/api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/confirm` | Y | CONTROL_VERIFIED | HIGH | `confirm_dinamic_scanner_txt_import` | backend/src/api/routes/v3/dinamic_scanner_txt_imports.py:195 |
| EP-0177 | POST | `/api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/preview` | Y | CONTROL_VERIFIED | HIGH | `preview_dinamic_scanner_txt_import` | backend/src/api/routes/v3/dinamic_scanner_txt_imports.py:162 |

## Module: `docs` (8)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0212 | GET | `/docs` | N | NOT_APPLICABLE | MEDIUM | `swagger_ui_html` | fastapi/applications.py: |
| EP-0213 | HEAD | `/docs` | N | NOT_APPLICABLE | INFORMATIONAL | `swagger_ui_html` | fastapi/applications.py: |
| EP-0214 | GET | `/docs/oauth2-redirect` | N | NOT_APPLICABLE | MEDIUM | `swagger_ui_redirect` | fastapi/applications.py: |
| EP-0215 | HEAD | `/docs/oauth2-redirect` | N | NOT_APPLICABLE | INFORMATIONAL | `swagger_ui_redirect` | fastapi/applications.py: |
| EP-0218 | GET | `/openapi.json` | N | NOT_APPLICABLE | MEDIUM | `openapi` | fastapi/applications.py: |
| EP-0219 | HEAD | `/openapi.json` | N | NOT_APPLICABLE | INFORMATIONAL | `openapi` | fastapi/applications.py: |
| EP-0221 | GET | `/redoc` | N | NOT_APPLICABLE | MEDIUM | `redoc_html` | fastapi/applications.py: |
| EP-0222 | HEAD | `/redoc` | N | NOT_APPLICABLE | INFORMATIONAL | `redoc_html` | fastapi/applications.py: |

## Module: `inventories` (40)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0055 | GET | `/api/v3/inventories/` | Y | POTENTIAL_BOLA | CRITICAL | `list_inventories` | backend/src/api/routes/v3/inventories.py:190 |
| EP-0056 | POST | `/api/v3/inventories/` | Y | AUTHORIZATION_UNKNOWN | MEDIUM | `create_inventory` | backend/src/api/routes/v3/inventories.py:111 |
| EP-0057 | POST | `/api/v3/inventories/bulk-soft-delete` | Y | AUTHORIZATION_UNKNOWN | HIGH | `bulk_soft_delete_inventories` | backend/src/api/routes/v3/inventories.py:137 |
| EP-0058 | GET | `/api/v3/inventories/ordered-capture-sessions/{session_id}` | Y | AUTHORIZATION_UNKNOWN | LOW | `get_ordered_capture_session` | backend/src/api/routes/v3/ordered_capture.py:67 |
| EP-0059 | POST | `/api/v3/inventories/ordered-capture-sessions/{session_id}/seal` | Y | AUTHORIZATION_UNKNOWN | MEDIUM | `seal_ordered_capture_session` | backend/src/api/routes/v3/ordered_capture.py:87 |
| EP-0060 | GET | `/api/v3/inventories/processing-provider-options` | Y | AUTHORIZATION_UNKNOWN | HIGH | `list_processing_provider_options` | backend/src/api/routes/v3/inventories.py:229 |
| EP-0061 | GET | `/api/v3/inventories/{inventory_id}` | Y | POTENTIAL_BOLA | CRITICAL | `get_inventory` | backend/src/api/routes/v3/inventories.py:409 |
| EP-0062 | PATCH | `/api/v3/inventories/{inventory_id}` | Y | POTENTIAL_BOLA | CRITICAL | `update_inventory` | backend/src/api/routes/v3/inventories.py:160 |
| EP-0163 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions` | Y | POTENTIAL_BOLA | HIGH | `list_capture_sessions` | backend/src/api/routes/v3/capture_sessions.py:273 |
| EP-0164 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions` | Y | POTENTIAL_BOLA | HIGH | `create_inventory_capture_session` | backend/src/api/routes/v3/capture_sessions.py:160 |
| EP-0165 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}` | Y | POTENTIAL_BOLA | HIGH | `get_capture_session_detail` | backend/src/api/routes/v3/capture_sessions.py:390 |
| EP-0166 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/cancel` | Y | POTENTIAL_BOLA | HIGH | `cancel_capture_session_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:234 |
| EP-0167 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/close` | Y | POTENTIAL_BOLA | HIGH | `close_capture_session_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:195 |
| EP-0168 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/compute-groups` | Y | POTENTIAL_BOLA | HIGH | `compute_capture_session_groups_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:407 |
| EP-0169 | GET | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups` | Y | POTENTIAL_BOLA | HIGH | `list_capture_session_groups_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:427 |
| EP-0170 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/materialize` | Y | POTENTIAL_BOLA | HIGH | `post_materialize_all_assigned_capture_session_groups` | backend/src/api/routes/v3/capture_sessions.py:499 |
| EP-0171 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/assign-existing` | Y | POTENTIAL_BOLA | HIGH | `assign_capture_session_group_to_existing_aisle_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:444 |
| EP-0172 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/create-aisle` | Y | POTENTIAL_BOLA | HIGH | `create_aisle_and_assign_capture_session_group_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:471 |
| EP-0173 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/materialize` | Y | POTENTIAL_BOLA | HIGH | `post_materialize_capture_session_group` | backend/src/api/routes/v3/capture_sessions.py:526 |
| EP-0174 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/preview` | Y | POTENTIAL_BOLA | HIGH | `post_materialized_capture_session_group_preview` | backend/src/api/routes/v3/capture_sessions.py:556 |
| EP-0175 | POST | `/api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/items` | Y | CONTROL_VERIFIED | MEDIUM | `upload_capture_session_staging_items_inventory_scope` | backend/src/api/routes/v3/capture_sessions.py:579 |
| EP-0181 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-assignments` | Y | POTENTIAL_BOLA | HIGH | `list_job_position_assignments` | backend/src/api/routes/v3/position_reconciliation.py:84 |
| EP-0182 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-detections` | Y | POTENTIAL_BOLA | HIGH | `list_job_position_detections` | backend/src/api/routes/v3/position_label_detections.py:34 |
| EP-0183 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation` | Y | POTENTIAL_BOLA | HIGH | `get_job_position_reconciliation` | backend/src/api/routes/v3/position_reconciliation.py:39 |
| EP-0184 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation/retry` | Y | POTENTIAL_BOLA | HIGH | `retry_job_position_reconciliation` | backend/src/api/routes/v3/position_reconciliation.py:126 |
| EP-0185 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-history` | Y | POTENTIAL_BOLA | HIGH | `get_position_history` | backend/src/api/routes/v3/position_overrides.py:125 |
| EP-0186 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override` | Y | POTENTIAL_BOLA | HIGH | `create_position_override` | backend/src/api/routes/v3/position_overrides.py:47 |
| EP-0187 | POST | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override/restore` | Y | POTENTIAL_BOLA | HIGH | `restore_automatic_position` | backend/src/api/routes/v3/position_overrides.py:88 |
| EP-0188 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/source-assets/{asset_id}/position-detections` | Y | POTENTIAL_BOLA | HIGH | `list_asset_position_detections` | backend/src/api/routes/v3/position_label_detections.py:64 |
| EP-0189 | GET | `/api/v3/inventories/{inventory_id}/jobs/{job_id}/unassigned-results` | Y | POTENTIAL_BOLA | HIGH | `list_job_unassigned_results` | backend/src/api/routes/v3/position_reconciliation.py:105 |
| EP-0190 | GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/download` | Y | CONTROL_VERIFIED | LOW | `download_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:448 |
| EP-0191 | GET | `/api/v3/inventories/{inventory_id}/labels/{label_id}/preview` | Y | CONTROL_VERIFIED | LOW | `preview_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:404 |
| EP-0192 | POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/render` | Y | CONTROL_VERIFIED | MEDIUM | `render_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:369 |
| EP-0193 | POST | `/api/v3/inventories/{inventory_id}/labels/{label_id}/replace` | Y | CONTROL_VERIFIED | MEDIUM | `replace_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:492 |
| EP-0200 | GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | Y | CONTROL_VERIFIED | LOW | `list_aisle_location_labels` | backend/src/api/routes/v3/aisle_locations.py:261 |
| EP-0201 | POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels` | Y | CONTROL_VERIFIED | MEDIUM | `issue_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:228 |
| EP-0202 | GET | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}` | Y | CONTROL_VERIFIED | LOW | `get_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:335 |
| EP-0203 | POST | `/api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate` | Y | CONTROL_VERIFIED | MEDIUM | `invalidate_aisle_location_label` | backend/src/api/routes/v3/aisle_locations.py:293 |
| EP-0204 | GET | `/api/v3/inventories/{inventory_id}/metrics` | Y | POTENTIAL_BOLA | CRITICAL | `get_inventory_metrics` | backend/src/api/routes/v3/inventories.py:426 |
| EP-0205 | GET | `/api/v3/inventories/{inventory_id}/recognition-config` | Y | CONTROL_VERIFIED | LOW | `get_inventory_recognition_config` | backend/src/api/routes/v3/inventories.py:317 |

## Module: `inventory_exports` (3)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0178 | GET | `/api/v3/inventories/{inventory_id}/export` | Y | POTENTIAL_BOLA | CRITICAL | `export_inventory_results` | backend/src/api/routes/v3/inventories.py:380 |
| EP-0179 | GET | `/api/v3/inventories/{inventory_id}/export/package` | Y | POTENTIAL_BOLA | CRITICAL | `export_inventory_package_zip` | backend/src/api/routes/v3/inventories.py:299 |
| EP-0180 | GET | `/api/v3/inventories/{inventory_id}/export/summary` | Y | POTENTIAL_BOLA | CRITICAL | `export_inventory_summary_csv` | backend/src/api/routes/v3/inventories.py:269 |

## Module: `jobs_processing` (21)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0096 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs` | Y | POTENTIAL_BOLA | HIGH | `list_aisle_jobs` | backend/src/api/routes/v3/aisles.py:736 |
| EP-0097 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_job_detail` | backend/src/api/routes/v3/aisles.py:899 |
| EP-0098 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts` | Y | POTENTIAL_BOLA | HIGH | `list_job_artifacts` | backend/src/api/routes/v3/aisles.py:1144 |
| EP-0099 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}` | Y | POTENTIAL_BOLA | HIGH | `get_job_artifact_metadata` | backend/src/api/routes/v3/aisles.py:1188 |
| EP-0100 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/download` | Y | POTENTIAL_BOLA | HIGH | `download_job_artifact` | backend/src/api/routes/v3/aisles.py:1212 |
| EP-0101 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/preview` | Y | POTENTIAL_BOLA | HIGH | `preview_job_artifact` | backend/src/api/routes/v3/aisles.py:1342 |
| EP-0110 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` | Y | POTENTIAL_BOLA | HIGH | `get_job_run_auditability` | backend/src/api/routes/v3/aisles.py:1085 |
| EP-0111 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel` | Y | POTENTIAL_BOLA | HIGH | `cancel_aisle_job` | backend/src/api/routes/v3/aisles.py:827 |
| EP-0112 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/errors` | Y | POTENTIAL_BOLA | HIGH | `get_job_errors` | backend/src/api/routes/v3/aisles.py:1730 |
| EP-0113 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` | Y | POTENTIAL_BOLA | HIGH | `get_job_execution_log` | backend/src/api/routes/v3/aisles.py:971 |
| EP-0114 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log.txt` | Y | POTENTIAL_BOLA | HIGH | `get_job_execution_log_txt` | backend/src/api/routes/v3/aisles.py:1010 |
| EP-0115 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log/page` | Y | POTENTIAL_BOLA | HIGH | `get_job_execution_log_page` | backend/src/api/routes/v3/aisles.py:1491 |
| EP-0116 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/hybrid-report` | Y | POTENTIAL_BOLA | HIGH | `get_job_hybrid_report` | backend/src/api/routes/v3/aisles.py:1053 |
| EP-0117 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/image-results` | Y | POTENTIAL_BOLA | HIGH | `list_job_image_results` | backend/src/api/routes/v3/image_results.py:61 |
| EP-0118 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry` | Y | POTENTIAL_BOLA | HIGH | `retry_aisle_job` | backend/src/api/routes/v3/aisles.py:867 |
| EP-0119 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry-chain` | Y | POTENTIAL_BOLA | HIGH | `get_job_retry_chain` | backend/src/api/routes/v3/aisles.py:1439 |
| EP-0120 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/timeline` | Y | POTENTIAL_BOLA | HIGH | `get_job_timeline` | backend/src/api/routes/v3/aisles.py:1604 |
| EP-0121 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability` | Y | POTENTIAL_BOLA | HIGH | `get_job_traceability` | backend/src/api/routes/v3/aisles.py:945 |
| EP-0142 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` | Y | CONTROL_VERIFIED | HIGH | `start_aisle_processing` | backend/src/api/routes/v3/aisles.py:575 |
| EP-0143 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing-state` | Y | POTENTIAL_BOLA | HIGH | `get_aisle_processing_state` | backend/src/api/routes/v3/aisles.py:650 |
| EP-0144 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing/recover` | Y | CONTROL_VERIFIED | HIGH | `recover_aisle_processing` | backend/src/api/routes/v3/aisles.py:686 |

## Module: `local_csv_imports` (3)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0194 | POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/confirm` | Y | CONTROL_VERIFIED | HIGH | `confirm_local_csv_import` | backend/src/api/routes/v3/local_csv_imports.py:165 |
| EP-0195 | POST | `/api/v3/inventories/{inventory_id}/local-csv-imports/preview` | Y | CONTROL_VERIFIED | HIGH | `preview_local_csv_import` | backend/src/api/routes/v3/local_csv_imports.py:133 |
| EP-0196 | GET | `/api/v3/inventories/{inventory_id}/local-csv-imports/{import_id}` | Y | CONTROL_VERIFIED | LOW | `get_local_csv_import` | backend/src/api/routes/v3/local_csv_imports.py:188 |

## Module: `local_inventory_packages` (3)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0197 | POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/confirm` | Y | CONTROL_VERIFIED | HIGH | `confirm_local_inventory_package` | backend/src/api/routes/v3/local_inventory_packages.py:215 |
| EP-0198 | POST | `/api/v3/inventories/{inventory_id}/local-inventory-packages/preview` | Y | CONTROL_VERIFIED | HIGH | `preview_local_inventory_package` | backend/src/api/routes/v3/local_inventory_packages.py:183 |
| EP-0199 | GET | `/api/v3/inventories/{inventory_id}/local-inventory-packages/{package_id}` | Y | CONTROL_VERIFIED | LOW | `get_local_inventory_package` | backend/src/api/routes/v3/local_inventory_packages.py:240 |

## Module: `observability` (1)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0206 | GET | `/api/v3/observability/metrics` | Y | AUTHORIZATION_UNKNOWN | LOW | `get_observability_metrics` | backend/src/api/routes/v3/observability.py:30 |

## Module: `ops` (3)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0216 | GET | `/health` | N | NOT_APPLICABLE | INFORMATIONAL | `health` | backend/src/api/server.py:258 |
| EP-0217 | GET | `/metrics` | N | NOT_APPLICABLE | HIGH | `metrics` | backend/src/api/server.py:240 |
| EP-0220 | GET | `/ready` | N | NOT_APPLICABLE | INFORMATIONAL | `ready` | backend/src/api/server.py:292 |

## Module: `positions` (7)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0133 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` | Y | POTENTIAL_BOLA | HIGH | `list_aisle_positions` | backend/src/api/routes/v3/positions.py:336 |
| EP-0134 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/by-position` | Y | POTENTIAL_BOLA | HIGH | `list_aisle_positions_by_position` | backend/src/api/routes/v3/positions.py:439 |
| EP-0135 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge` | Y | POTENTIAL_BOLA | HIGH | `confirm_merge_positions` | backend/src/api/routes/v3/positions.py:784 |
| EP-0136 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge/preview` | Y | POTENTIAL_BOLA | HIGH | `preview_merge_positions` | backend/src/api/routes/v3/positions.py:757 |
| EP-0137 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` | Y | POTENTIAL_BOLA | HIGH | `get_position_detail` | backend/src/api/routes/v3/positions.py:627 |
| EP-0138 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/code-scan-evidence` | Y | POTENTIAL_BOLA | HIGH | `get_position_code_scan_evidence` | backend/src/api/routes/v3/positions.py:673 |
| EP-0139 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews` | Y | POTENTIAL_BOLA | HIGH | `submit_review_action` | backend/src/api/routes/v3/reviews.py:114 |

## Module: `preliminary` (2)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0140 | PUT | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}` | Y | CONTROL_VERIFIED | MEDIUM | `upsert_preliminary_detection` | backend/src/api/routes/v3/preliminary_detections.py:38 |
| EP-0141 | GET | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-reconciliations` | Y | POTENTIAL_BOLA | HIGH | `list_preliminary_reconciliations` | backend/src/api/routes/v3/preliminary_reconciliations.py:119 |

## Module: `review_queue` (1)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0207 | GET | `/api/v3/review-queue/positions` | Y | AUTHORIZATION_UNKNOWN | LOW | `list_review_queue_positions` | backend/src/api/routes/v3/review_queue.py:137 |

## Module: `server_reprocess` (1)
| ID | Method | Path | Auth | BOLA | DAST | Handler | File:line |
|----|--------|------|------|------|------|---------|-----------|
| EP-0147 | POST | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reprocess` | Y | POTENTIAL_BOLA | HIGH | `reprocess_aisle_positioning` | backend/src/api/routes/v3/positioning_operational.py:134 |
