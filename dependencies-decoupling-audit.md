# Audit & Refactor Plan — `src.api.dependencies`

## 1. Executive Summary

**Scope audited.** `backend/src/api/dependencies.py` (3,651 lines, 203 top-level
functions, 8 private helpers, no classes). This is the approximately 4,000-line
file referenced in the request; `backend/src/auth/dependencies.py` is a separate
147-line authentication module and is not the monolith.

The file is principally the API composition root: it assembles application use
cases from ports/repositories supplied by `src.runtime.v3_deps` and
`AppContainer`. It also contains request-scoped FastAPI guards, small adapter
providers, local-import construction code, and a few operational factories. It
does **not** contain normal SQL queries itself. The main problem is aggregation
of unrelated bounded contexts in a single public module, not a single business
algorithm.

There are 76 direct import statements from `src.api.dependencies` in 75 files:
30 v3 route modules, `runtime/app_container.py`, one worker, and 43 test files.
The functions are also FastAPI override keys. Consequently, moving code while
changing the callable object or route imports can silently defeat
`app.dependency_overrides`.

Overall risk is **high but manageable**. A package split is suitable, provided
that the public import path and callable identity are preserved during every
phase. The existing deferred import from `AppContainer` to
`build_confirm_local_csv_import` is the concrete cycle to protect.

## 2. Current Responsibility Map

The table groups the complete set of relevant symbols; ranges are source lines
in the audited file. `v3 deps` means the stable repository/provider functions in
`src.runtime.v3_deps`; `container` means `src.runtime.app_container`.

| Symbol / group | Responsibility | Consumers | Dependencies | Risk |
|---|---|---|---|---|
| `get_artifact_storage`, `get_worker_launch_service_dep`, `get_*repo` adapters (231-306; 2338-2378; 3205-3226) | Expose container/v3-deps infrastructure to FastAPI | routes, workers, many overrides | container, `v3_deps` | High: high fan-in/override keys |
| `get_job_stale_reconciler`, `get_finalization_assessment_service`, `get_*policy`, `get_access_principal`, result/evidence helpers (240-305, 375-398, 2570-2612) | Cross-cutting services, policies and artifact evidence | aisle, positions, observability routes | repositories, clock, settings, storage | High |
| `require_inventory_client_scope`, `require_client_scope`, `require_capture_session_upload_scope`, `require_raspberry_device_token` (309-372, 401-432) | Authentication-adjacent scope/device guards and HTTP error mapping | inventory/asset/capture/raspberry routes; tests override them | `get_current_admin`, repos, FastAPI Header | **High** security behavior |
| Inventory/client/supplier base and exports (435-714, 1793-1976) | Construct CRUD, recognition, export, supplier reference/prompt/profile use cases | inventories, clients, suppliers routes | repos, clock, settings/container | Medium |
| Aisle lifecycle and assets (717-1007, 1499-1665) | Construct lifecycle, job launch/recovery, processing, upload, finalization and preliminary reconciliation use cases | aisles/assets/finalization/preliminary routes | repos, storage, clock, policies, worker | High |
| Local CSV/package/scanner import (1010-1496) | Feature-gated import preview/confirmation plus recovery-builder support | three import routes, `AppContainer`, unit tests | settings, container, repositories, storage | **High**: only proven container→API dependency |
| Code scanning (1668-1790) | Scanner/content adapters and scan use cases | code-scan routes/tests | container, storage, repos, clock | Medium |
| Position/review/merge (1979-2315) | Position read/review mutations, merge, job-read providers | positions, reviews, review queue routes | repos, principal, clock, lifecycle sync | High |
| Processing observability/image results (2318-2567) | Processing-event builders and manual/image-result use cases | image-result and processing-observability routes | container-built services, repos | High: private factories close over container |
| Analytics/benchmark/audit (2590-2736) | Auditability, metrics, comparisons, analytics factories | analytics/observability/aisle routes | repos, storage, result context | Medium |
| Capture and ordered capture (2739-3102) | Capture-session lifecycle/materialization and ordered-capture providers | capture/ordered-capture routes | capture repos, storage, clock, access policy | High: uploads and idempotency |
| Aisle locations, labels, positioning (3105-3651) | Location/label CRUD and positioning/reconciliation/override factories | six position/location routes | container, repos, storage, signing, settings | High: largest and most coupled domain group |

### Classification: what belongs in a dependency layer

* **A — legitimate dependencies:** all request guards; container/`v3_deps`
  adapters; and the thin `get_*_use_case` providers that only wire explicit
  collaborators.
* **B — dependency with misplaced construction logic:** providers that load
  settings and build several subordinate policies/adapters, notably
  `get_upsert_preliminary_detection_use_case`,
  `get_persist_authoritative_local_code_scan_use_case`, the processing-event
  builders, positioning/label providers, and several import/package providers.
  They may remain API factories initially, but should delegate construction to
  existing container builders or application-level builders in a later, separate
  change.
* **C — not FastAPI dependencies:** `_build_preview_local_csv_import`,
  `_build_import_canonical_position_materializer`,
  `build_confirm_local_csv_import`, `_dinamic_scanner_txt_import_enabled`,
  `_csv_import_pipeline_enabled`, `_build_processing_scope_validator`,
  `_build_processing_idempotency_service`, `_build_processing_event_publisher`,
  and `_build_queue_asset_command_use_case`. They are composition helpers. In
  particular `build_confirm_local_csv_import` is called by `AppContainer`, so it
  must not remain coupled to an HTTP-named module long term.

## 3. Current Dependency Graph

```text
routes/v3 (30 modules) ── Depends(provider) ──> src.api.dependencies (203 functions)
tests (43 direct importers) ── dependency_overrides[provider] ─┘
worker/preliminary_reconciliation_worker ──> provider
                                              │
                 request guards ─────────────┼──> src.auth.dependencies.get_current_admin
                                              ├──> src.runtime.v3_deps (repos/clock/services)
                                              ├──> src.runtime.app_container (adapters/builders)
                                              ├──> src.application (use cases, policies, ports)
                                              └──> src.config / API services

src.runtime.app_container -- local import --> build_confirm_local_csv_import
```

Internal DI chains are real rather than merely lexical. Examples: `get_start_aisle_processing_use_case`
depends on job launch, stale reconciliation, inventory policy and 10 lower-level
providers; `get_reprocess_aisle_positioning_use_case` depends on processing
status, start processing and reconciliation; capture group assignment depends on
`get_create_aisle_use_case`; export comparison depends on
`get_compare_aisle_runs_use_case`. FastAPI resolves these providers per request
with its default request cache; no `use_cache=False`, `Security(...)`,
`Annotated[..., Depends(...)]`, async provider, or closure/factory used directly
as a `Depends` target was found in this module.

## 4. Architectural Problems

1. **Composition root has no domain boundary.** Imports span 100+ application
   use cases and unrelated concerns from device authentication to PDF labels.
2. **Mixed resolution styles.** Some providers inject `v3_deps`, others call the
   container inside their body, and others build compound objects from settings.
   This makes a provider's test seam non-obvious.
3. **Public surface is accidental.** 195 non-private functions are importable;
   routes and tests import implementation-level repository adapters directly.
4. **HTTP and non-HTTP composition share a module.** The CSV confirmation
   builder is imported lazily by the runtime container. That weakens API/runtime
   layering and explains the existing deferred import.
5. **High fan-in anchors.** `get_artifact_storage`, repository adapters,
   `get_inventory_access_policy`, `get_inventory_status_reconciler`,
   `get_result_context_resolver`, and `get_access_principal` fan into multiple
   domains. They should move last or retain a compatibility export.

## 5. Proposed Target Architecture

Do not add a DI framework. Retain FastAPI functions and the current runtime
container. Split only along demonstrated route/domain cohesion:

```text
src/api/
  dependencies/                 # replaces dependencies.py atomically
    __init__.py                 # compatibility public surface only
    infrastructure.py           # adapters, storage, clock/container bridge
    access.py                   # principal, client/inventory/capture/device guards
    inventory.py                # inventory, clients, suppliers, exports/recognition
    aisles.py                   # aisle lifecycle, assets, processing, code scans
    imports.py                  # CSV/package/scanner imports and non-HTTP builders
    positions.py                # reviews, merges, image/processing results, positioning
    capture.py                  # capture and ordered-capture
    analytics.py                # auditability, analytics, benchmark, observability
    locations.py                # aisle locations and label artifacts
```

`infrastructure.py` owns only API-facing aliases to `v3_deps`/container. It
should not reproduce repository construction. `access.py` owns the sensitive
guards and their exception mapping. The remaining modules assemble use cases for
the route areas that consume them. `imports.py` is the exception: it should first
preserve the container's lazy import path via `__init__`; after a dedicated
runtime change, move `build_confirm_local_csv_import` to a neutral runtime or
application composition module.

## 6. Symbol Migration Map

Every top-level function is covered below; exact symbol lists deliberately make
this implementable without rediscovery.

| Current symbols | Proposed destination | Reason | Risk |
|---|---|---|---|
| `get_artifact_storage`, `get_worker_launch_service_dep`, `get_job_stale_reconciler`, `get_finalization_assessment_service`, `get_artifact_publication_outbox_store`, `get_artifact_manifest_store`, `get_supplier_extraction_profile_repo`, `get_client_supplier_label_profile_repo`, `get_result_evidence_repo`, `get_result_evidence_query_service`, `get_operational_execution_config_resolver`, `get_result_context_resolver`, `get_inventory_access_policy`, `get_capture_session_access_policy`, `get_inventory_status_reconciler`, `get_aisle_review_lifecycle_sync`, `get_position_materialization_service`, `get_job_source_asset_repo`, `get_manual_image_coverage_repo`, `get_job_image_coverage_repo`, `get_manual_image_result_uow_factory`, `get_processing_event_repo`, `get_processing_action_idempotency_service`, `get_job_artifact_catalog_service`, `get_job_retry_chain_service`, `get_aisle_location_label_artifact_repo`, `get_image_position_label_detection_repo`, `get_position_reconciliation_repo`, `get_materialized_position_identity_reader`, `get_client_position_label_repo`, `get_manual_position_override_repo` | `infrastructure.py` | Cross-cutting adapters/services | High |
| `require_inventory_client_scope`, `require_client_scope`, `require_raspberry_device_token`, `get_access_principal`, `require_capture_session_upload_scope` | `access.py` | Security and tenant scope are cohesive | High |
| `get_create_inventory_use_case`, `get_update_inventory_name_use_case`, `get_soft_delete_inventories_use_case`, `get_create_client_use_case`, `get_update_client_use_case`, `get_create_client_supplier_use_case`, `get_list_inventories_use_case`, `get_list_clients_use_case`, `get_list_client_suppliers_use_case`, `get_list_inventory_list_items_use_case`, `get_inventory_recognition_config_use_case`, `get_client_recognition_config_use_case`, `get_raspberry_recognition_config_use_case`, `get_get_inventory_use_case`, `get_get_client_use_case`, `get_get_client_supplier_use_case`, `get_export_inventory_results_use_case`, `get_export_aisle_results_csv_use_case`, `get_export_inventory_summary_csv_use_case`, `get_export_inventory_package_zip_use_case`, `get_export_aisle_business_csv_use_case`, `get_get_inventory_metrics_use_case`, `get_upload_supplier_reference_images_use_case`, `get_list_supplier_reference_images_use_case`, `get_get_supplier_reference_image_use_case`, `get_delete_supplier_reference_image_use_case`, `get_list_supplier_prompt_configs_use_case`, `get_create_supplier_prompt_config_version_use_case`, `get_get_active_supplier_prompt_config_use_case`, `get_activate_supplier_prompt_config_version_use_case`, `get_get_supplier_prompt_config_use_case`, `get_list_supplier_extraction_profiles_use_case`, `get_get_active_supplier_extraction_profile_use_case`, `get_get_supplier_extraction_profile_by_version_use_case`, `get_create_supplier_extraction_profile_version_use_case`, `get_activate_supplier_extraction_profile_version_use_case`, `get_test_label_recognition_code_use_case`, `get_clone_supplier_extraction_profile_use_case`, `get_list_supplier_reference_annotations_use_case`, `get_replace_supplier_reference_annotations_use_case`, `get_list_client_supplier_label_profiles_use_case`, `get_upsert_client_supplier_label_profile_use_case` | `inventory.py` | Inventory/client/supplier route cohesion | Medium |
| `get_create_aisle_use_case`, `get_aisle_identification_configuration_query`, `get_update_aisle_code_use_case`, `get_deactivate_aisle_use_case`, `get_activate_aisle_use_case`, `get_list_aisles_by_inventory_use_case`, `get_list_aisles_with_status_use_case`, `get_aisle_job_launch_service`, `get_start_aisle_processing_use_case`, `get_get_aisle_processing_status_use_case`, `get_cancel_aisle_job_use_case`, `get_recover_stale_job_use_case`, `get_recover_aisle_processing_use_case`, `get_retry_aisle_job_use_case`, `get_upload_aisle_assets_use_case`, `get_list_aisle_assets_use_case`, `get_upsert_preliminary_detection_use_case`, `get_persist_authoritative_local_code_scan_use_case`, `get_evaluate_authoritative_aisle_readiness`, `get_finalize_authoritative_aisle_use_case`, `get_reconcile_preliminary_detections_use_case`, `get_process_preliminary_reconciliations_use_case`, `get_list_preliminary_reconciliations_use_case`, `get_delete_aisle_source_asset_use_case`, `get_code_scanner`, `get_source_asset_content_reader`, `get_match_aisle_code_scan_detections_use_case`, `get_run_aisle_code_scan_use_case`, `get_list_aisle_code_scans_use_case`, `get_summarize_aisle_code_scans_use_case`, `get_get_position_code_scan_evidence_use_case`, `get_get_aisle_code_scan_review_signals_use_case`, `get_export_aisle_code_scans_use_case` | `aisles.py` | Lifecycle/assets/scans form one route-facing workflow | High |
| `_build_preview_local_csv_import`, `_build_import_canonical_position_materializer`, `build_confirm_local_csv_import`, `get_preview_local_csv_import_use_case`, `get_confirm_local_csv_import_use_case`, `get_get_local_csv_import_use_case`, `get_preview_local_inventory_package_use_case`, `get_confirm_local_inventory_package_use_case`, `get_get_local_inventory_package_use_case`, `_dinamic_scanner_txt_import_enabled`, `_csv_import_pipeline_enabled`, `get_preview_dinamic_scanner_txt_import_use_case`, `get_confirm_dinamic_scanner_txt_import_use_case` | `imports.py` | Feature flags and shared import builders | High |
| `get_list_aisle_positions_use_case`, `get_list_review_queue_use_case`, `get_get_position_detail_use_case`, `get_confirm_position_use_case`, `get_update_product_quantity_use_case`, `get_update_product_sku_use_case`, `get_update_position_code_use_case`, `get_mark_position_unknown_use_case`, `get_mark_position_image_mismatch_use_case`, `get_delete_position_use_case`, `get_preview_merge_positions_use_case`, `get_confirm_merge_positions_use_case`, `get_run_aisle_merge_use_case`, `get_get_aisle_merge_results_use_case`, `get_list_aisle_jobs_use_case`, `get_resolve_aisle_job_for_inventory_read_use_case`, `get_observability_inventory_guard`, `get_list_job_image_results_use_case`, `_build_processing_scope_validator`, `_build_processing_idempotency_service`, `_build_processing_event_publisher`, `_build_queue_asset_command_use_case`, `get_list_asset_processing_use_case`, `get_get_asset_processing_detail_use_case`, `get_list_processing_events_use_case`, `get_reprocess_asset_use_case`, `get_retry_asset_persistence_use_case`, `get_send_asset_to_external_use_case`, `get_invalidate_asset_result_use_case`, `get_single_asset_command_executor`, `get_create_manual_image_result_use_case`, `get_position_override_scope_resolver`, `get_effective_position_reader`, `get_manage_position_override_use_case`, `get_list_position_override_history_use_case`, `get_reconcile_job_positions_use_case`, `get_aisle_operational_positioning_view_use_case`, `get_aisle_positioning_sequence_use_case`, `get_reprocess_aisle_positioning_use_case` | `positions.py` | Position review/reconciliation and result processing share repositories/policies | High |
| `get_run_auditability_service`, `get_observability_metrics_service`, `get_compare_aisle_runs_use_case`, `get_compare_many_aisle_runs_use_case`, `get_promote_aisle_operational_job_use_case`, `get_export_aisle_benchmark_run_csv_use_case`, `get_export_aisle_benchmark_compare_csv_use_case`, `get_analytics_query_service`, `get_analytics_cost_summary_service` | `analytics.py` | Read-only analytics/audit/benchmark boundary | Medium |
| `get_create_capture_session_use_case`, `get_close_capture_session_use_case`, `get_cancel_capture_session_use_case`, `get_list_capture_sessions_use_case`, `get_get_capture_session_detail_use_case`, `get_capture_staging_time_metadata_extractor`, `get_upload_capture_session_staging_items_use_case`, `get_update_capture_session_clock_offset_use_case`, `get_compute_capture_session_assignment_preview_use_case`, `get_compute_capture_session_groups_use_case`, `get_get_capture_session_groups_use_case`, `get_assign_capture_session_group_to_existing_aisle_use_case`, `get_create_aisle_and_assign_capture_session_group_use_case`, `get_compute_materialized_capture_session_group_preview_use_case`, `get_materialize_capture_session_group_use_case`, `get_materialize_capture_session_use_case`, `get_create_ordered_capture_session_use_case`, `get_get_ordered_capture_session_use_case`, `get_seal_ordered_capture_session_use_case` | `capture.py` | Capture lifecycle, materialization, ordered capture | High |
| `get_create_aisle_location_use_case`, `get_list_aisle_locations_use_case`, `get_get_aisle_location_use_case`, `get_update_aisle_location_use_case`, `get_issue_aisle_location_label_use_case`, `get_render_aisle_location_label_use_case`, `get_download_aisle_location_label_use_case`, `get_get_aisle_location_label_use_case`, `get_replace_aisle_location_label_use_case`, `get_batch_render_aisle_location_labels_use_case`, `get_list_aisle_location_labels_use_case`, `get_invalidate_aisle_location_label_use_case` | `locations.py` | Location label lifecycle | Medium |

## 7. Backward Compatibility Strategy

Do **not** create `src/api/dependencies/` while retaining
`src/api/dependencies.py`. A same-name module and package have import-resolution
ambiguity and make the deployed layout dependent on import machinery. Use one
atomic filesystem transition: rename the old file into the new package during a
single change, create `dependencies/__init__.py`, and re-export every current
public symbol from its target submodule. Existing code can therefore continue to
use `from src.api.dependencies import X`.

`__init__.py` is viable only as a temporary/intentional facade, with explicit
imports (and ideally `__all__`), not wildcard imports. Route imports stay
unchanged in early phases. This preserves both the import path and the actual
function object, so `app.dependency_overrides[X]` remains keyed to the callable
the route registered. Do not wrap providers in forwarding functions: wrappers
change identity and break overrides.

After each domain is stable, route modules may optionally import their specific
submodule; tests must import the same callable object. Keep facade exports until
all internal consumers and documented extension points are migrated, then make
their removal a versioned breaking change.

## 8. Circular Dependency Risks

* **Existing, evidenced, HIGH:** `AppContainer.get_local_csv_import_recovery_service`
  lazily imports `src.api.dependencies.build_confirm_local_csv_import`
  (`backend/src/runtime/app_container.py:749`). It is deferred precisely to
  avoid import-time circularity. During the package transition, re-export this
  symbol immediately from `dependencies.__init__`; do not import
  `AppContainer` at a new module's import time beyond current behavior.
* **Potentially introduced, HIGH:** `imports.py` importing the container while
  `AppContainer` imports `dependencies.imports` directly would become eager.
  Preserve the existing lazy facade import first; later move this builder to a
  neutral composition location and update the container in its own phase.
* **Potentially introduced, MEDIUM:** `access.py` must depend on auth and
  application policies, never on routes. Domain modules must not import each
  other for a provider; shared adapters/policies belong in `infrastructure.py`.
  Current evidence does not show an application/service module importing this
  API module, other than the container's deferred CSV builder.

## 9. FastAPI DI Impact

The providers use `Depends(...)` as default parameter values; their dependency
chains and default request caching are part of the contract. No `Security`,
`Annotated`, async dependency, `use_cache=False`, or direct dynamic dependency
target was found. `Header` is used by the Raspberry token guard. Preserve
signature, default object, annotation, and the provider object itself exactly.

Sensitive order: `require_capture_session_upload_scope` intentionally runs
before multipart work and maps domain exceptions itself; `require_inventory_client_scope`
and `require_client_scope` likewise map errors raised during DI. Moving them
without their imports or changing their signature/order can change 404/409 to
500 or permit expensive upload processing before authorization.

## 10. Test Impact

43 test files directly import this module. They frequently set
`app.dependency_overrides` for repository adapters, storage, guards and use-case
providers. Examples include review-action/recomputed-consolidation overrides,
capture upload/storage overrides, tenant-isolation repository overrides, and
route wiring/error mapping tests. `tests/runtime/test_position_materialization_runtime.py:251`
also monkeypatches the module's `get_app_container` attribute.

Tests must initially remain unchanged through facade exports. Before any route
import is changed, add/retain tests proving: (1) the facade attribute `is` the
submodule provider; (2) an override set using the facade is honored by the
route; (3) the container's CSV recovery builder imports successfully. Search
again for `dependency_overrides`, `monkeypatch`, `patch`, and imports after each
phase; no dynamic `importlib`/`__import__` usage targeting this module was found.

## 11. Migration Plan

### Phase 0 — characterization and package cutover prerequisite

**Objective:** establish import/identity regression coverage before restructuring.
**Files:** tests plus future package layout only. **Symbols:** facade sample from
each high-risk group and CSV builder. **Consumers:** all routes/tests indirectly.
**Risks:** package/file collision; override identity. **Validations:** import
smoke, focused API override tests, full pytest/lint/typecheck commands actually
defined by the repository/CI. **Close:** facade and submodule objects are
identical; no import cycle.

### Phase 1 — infrastructure and access

**Objective:** move low-line-count adapters and security guards first, retaining
facade exports. **Files:** `infrastructure.py`, `access.py`, `__init__.py`.
**Symbols:** first two rows of the migration map. **Consumers:** almost every
route, so imports remain facade-based. **Risk:** high but mechanically isolated.
**Validations:** auth/tenant/capture pre-spool/raspberry tests and override
identity tests. **Rollback:** revert only package contents; facade path remains.
**Close:** all previous imports and security statuses unchanged.

### Phase 2 — inventory, supplier and analytics providers

**Objective:** extract cohesive mostly read/CRUD construction. **Files:**
`inventory.py`, `analytics.py`, facade. **Consumers:** inventories, clients,
suppliers, analytics and observability routes. **Risks:** exports use container
internals; recognition/settings behavior. **Validations:** inventory wiring,
supplier-reference, analytics-cost and benchmark tests. **Close:** provider
object identities and result contracts match.

### Phase 3 — capture and location labels

**Objective:** extract two self-contained route families. **Files:**
`capture.py`, `locations.py`, facade. **Symbols:** capture/location rows above.
**Risks:** multipart artifact storage, idempotent materialization, signing/PDF
limits. **Validations:** capture-session materialization/sprint/upload tests and
location/label route tests. **Close:** upload authorization occurs before spool;
idempotency path is unchanged.

### Phase 4 — aisles and imports

**Objective:** isolate aisle lifecycle/scans and import factories without
changing runtime layering. **Files:** `aisles.py`, `imports.py`, facade.
**Consumers:** aisle/assets/scans/import/finalization routes, worker, container.
**Risks:** highest; job chains, settings feature flags, and the proven CSV cycle.
**Validations:** import feature-matrix/scanner tests, aisle wiring, upload stream
close, worker import smoke, `AppContainer` recovery construction. **Close:** no
new cycle and all container deferred calls work.

### Phase 5 — positions and processing results

**Objective:** extract the most coupled operational graph last. **Files:**
`positions.py`, facade. **Consumers:** positions/reviews/image-results/processing
/positioning routes. **Risks:** many collaborator settings and override seams.
**Validations:** review actions, merge DI/endpoints, image results, result
evidence, positioning reprocess/error mapping tests. **Close:** exact provider
and nested dependency graph resolves under FastAPI.

### Phase 6 — targeted layering cleanup, optional import migration

**Objective:** only after structural parity, move C helpers out of API ownership
and optionally migrate route imports to domain modules. **Files:** neutral
runtime/application composition module, `AppContainer`, imports facade/tests.
**Risks:** cycle reintroduction and public-contract removal. **Validations:** all
tests plus import graph check. **Close:** container no longer imports API; facade
exports retained until a separately approved deprecation window ends.

## 12. Final Recommendation

```text
CURRENT_FILE:
backend/src/api/dependencies.py

CURRENT_SIZE:
3,651 lines; 203 functions (195 public by underscore convention)

TARGET_STRUCTURE:
dependencies/{__init__,infrastructure,access,inventory,aisles,imports,
              positions,capture,analytics,locations}.py

ESTIMATED_FINAL_dependencies.py:
0 lines after atomic package replacement; __init__.py should remain a small,
explicit compatibility facade rather than a new monolith.

MIGRATION_PHASES:
7 (Phase 0 through Phase 6)

BLOCKERS:
No blocker to begin Phase 0. Block structural extraction of `imports.py` until
the AppContainer → build_confirm_local_csv_import lazy dependency is protected
by a facade identity/import test.

READY_FOR_DECOUPLING:
YES, after Phase 0 characterization tests are added and the package/file
cutover is planned as one atomic change.
```

The recommended first implementation change is not a business refactor: it is a
minimal package conversion plus a compatibility facade and identity tests. Keep
all route imports unchanged until that safety net is green.
