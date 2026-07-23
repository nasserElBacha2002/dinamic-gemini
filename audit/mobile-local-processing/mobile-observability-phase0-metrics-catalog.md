# Mobile Observability Phase 0 — Metrics Catalog

| Métrica | Nivel | Inicio | Fin | Unidad | Persistencia | Sensibilidad |
| ------- | ----- | ------ | --- | ------ | ------------ | ------------ |
| capture_to_queued_ms | imagen | session.created / detect | photo.queued | ms | event attrs / marks | baja |
| queued_to_prepare_started_ms | imagen | photo.queued | photo.prepare_started | ms | event attrs | baja |
| prepare_ms | imagen | prepare start | prepare end | ms | durationMs + attrs | baja |
| original_bytes | imagen | gallery/re-stat | — | bytes | attrs + SQLite photo.original_size | baja |
| prepared_bytes | imagen | after transform | — | bytes | attrs + upload_size | baja |
| compression_ratio | imagen | original/prepared | — | ratio | attrs | baja |
| original_width / original_height | imagen | MediaStore | — | px | attrs | baja |
| prepared_width / prepared_height | imagen | manipulator result | — | px | attrs | baja |
| transformation_profile | imagen | prepare | — | enum | attrs | baja |
| transformation_version | imagen | constant phase0-v1 | — | string | attrs | baja |
| queued_to_upload_started_ms | imagen | prepared/queued mark | upload start | ms | attrs | baja |
| upload_ms | imagen/batch | HTTP start | HTTP end | ms | durationMs | baja |
| upload_attempt_count | imagen | photo.upload_attempts | — | count | attrs | baja |
| upload_http_status | imagen/batch | response/error | — | int/null | attrs | baja |
| upload_error_code | imagen/batch | normalized catalog | — | enum | attrs | baja |
| batch_id | batch | session.upload_batch_id | — | id | event | baja |
| session_id | batch/trabajo | capture session | — | id | event | baja |
| job_id / server_job_id | trabajo | process response | — | id | event | baja |
| image_count | batch | packed files | — | count | attrs | baja |
| total_original_bytes | batch | sum originals | — | bytes | attrs | baja |
| total_prepared_bytes | batch | sum upload sizes | — | bytes | attrs | baja |
| batch_queue_wait_ms | batch | (derived via photo waits) | — | ms | photo-level | baja |
| batch_upload_ms | batch | batch HTTP start | end | ms | durationMs | baja |
| batch_attempt_count | batch | attempt marker | — | count | attrs | baja |
| network_type | batch/imagen | NetInfo snapshot | — | enum | attrs | baja |
| effective_concurrency | batch | activeRequests | — | count | attrs | baja |
| is_connected / is_internet_reachable / connection_type | conectividad | NetInfo | — | bool/string | attrs | baja (sin SSID/IP) |
| session_created_to_first_upload_ms | trabajo | session.created | first upload | ms | attrs | baja |
| session_created_to_all_uploads_completed_ms | trabajo | session.created | all uploaded | ms | attrs | baja |
| all_uploads_completed_to_process_requested_ms | trabajo | all uploads mark | process request | ms | attrs | baja |
| process_request_ms | trabajo | POST /process | response | ms | durationMs | baja |
| process_requested_to_job_started_ms | trabajo | process accepted | running observed | ms | attrs | baja |
| job_started_to_first_result_ms | trabajo | job started | first positions/terminal | ms | attrs | baja |
| job_started_to_terminal_ms | trabajo | job started | terminal | ms | attrs | baja |
| capture_to_first_server_result_ms | trabajo | session.created | first result | ms | attrs | baja |
| capture_to_job_terminal_ms | trabajo | session.created | terminal | ms | attrs | baja |
| capture_to_full_sync_ms | trabajo | session.created | terminal (phase0=terminal) | ms | attrs | baja |
| total_images / uploaded_images / failed_images | trabajo | photo rows at terminal | — | count | attrs | baja |
| retryable_failures / terminal_failures | trabajo | upload statuses | — | count | attrs | baja |
| error_code (normalized) | error | failure site | — | enum | attrs | baja |

Normalized error codes: `PREPARE_*`, `UPLOAD_*`, `PROCESS_REQUEST_FAILED`, `JOB_*`, `QUEUE_RESTORE_FAILED`, `UNKNOWN_ERROR`.
