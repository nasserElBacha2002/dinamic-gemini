# G2 — Enforce client_id on new inventories

## 1. Executive summary

**Final status: G2_READY_FOR_REVIEW**

New inventory creation now requires a non-empty `client_id` that resolves to an existing client on the API and in the create use case. The UI no longer offers a legacy “no client” path for new inventories. Historical rows with `client_id = NULL` remain supported at read/response level; the database column stays nullable (NOT NULL deferred to G4.1). One API test that previously created a null-client inventory via POST now simulates legacy reads with a thin `InventoryRepository` proxy so the supplier-without-client aisle rule stays covered.

## 2. Scope implemented

- Backend: `CreateInventoryRequest.client_id` required; reject blank/whitespace; explicit JSON `null` → 422 (Pydantic).
- Backend: `CreateInventoryCommand` / `CreateInventoryUseCase` require `client_id`; validate existence; `ValueError` for strip-empty (defense in depth); route maps `ValueError` → 422.
- Frontend: `CreateInventoryDialog` requires client selection; Spanish validation strings; loading/error/empty states; create button disabled when clients cannot be used.
- Frontend: `CreateInventoryRequest.client_id` required in types.
- Tests: use-case and API tests updated; legacy null-create test removed; aisle 409 scenario preserved via repository read proxy.
- Drift script: `static_legacy_exposure` notes updated (no longer points at removed i18n key / optional schema).

Out of scope (unchanged): NOT NULL on `inventories.client_id`, backfill, aisle supplier G3 work, `inventory_visual_references`, prompt fallback, pipeline, inventory detail legacy warnings.

## 3. Backend changes

| Area | Change |
|------|--------|
| `inventory_schemas.py` | `client_id: str` required with strip + non-empty validation. |
| `create_inventory.py` | `CreateInventoryCommand` fields reordered (`client_id` before defaulted `processing_mode`); always resolve client; strip-empty → `ValueError`. |
| `inventories.py` (route) | `except ValueError` → HTTP 422 with `detail=str(exc)`. |

## 4. Frontend changes

| Area | Change |
|------|--------|
| `CreateInventoryDialog.tsx` | Removed legacy “Sin cliente” option; disabled placeholder; `nameError` / `clientError`; submit sends required `client_id`; create disabled when clients loading/failed/empty. |
| `requests.ts` | `CreateInventoryRequest.client_id` required (`string`). |
| `es` / `en` `translation.json` | Updated client empty/load copy; added `client_placeholder`, `validation_client_required`, `validation_client_required_create_first`; removed `client_none_option`. |

## 5. Tests updated

| Test / helper | Purpose |
|---------------|---------|
| `tests/support/api_v3_test_helpers.py` | `create_test_client`, `create_test_inventory` for API tests needing a valid client. |
| `test_create_inventory.py` | All creates pass `client_id`; blank strip → `ValueError`; invalid id → `ClientNotFoundError`. |
| `test_inventories_v3_wiring.py` | 201 responses assert non-null `client_id`; null/missing body → 422. |
| `test_aisles_v3_wiring.py` | `_pinv` helper; `test_post_aisle_with_supplier_when_inventory_has_no_client_returns_409_structured` uses `_InventoryReadProxyClearClient` + `get_app_container().get_inventory_repo()`. |
| `test_inventory_export_api.py`, capture session API tests | Inventory POSTs use helper. |
| `test_inventory_status_lifecycle_and_backfill.py` | Seed client in `MemoryClientRepository` and pass `client_id` on create. |
| `CreateInventoryDialog.creationFlow.test.tsx` | Client required on happy path; no “Sin cliente” option; validation when no client selected. |

## 6. Legacy compatibility retained

- **Read paths:** `InventoryResponse` / list rows still expose `client_id: str | None` for historical NULL.
- **Database:** No migration; `inventories.client_id` remains nullable until G4.1.
- **Detail UX:** No change to inventory detail legacy warnings (explicitly out of scope for removal).
- **Aisle supplier rule:** Still enforced when the inventory has no client **in the domain read model** (simulated in tests where API can no longer create such a row).

## 7. Validation results

Commands run (all succeeded in this environment):

```bash
cd backend && python -m pytest tests/application/use_cases/test_create_inventory.py \
  tests/api/test_inventories_v3_wiring.py tests/api/test_inventory_export_api.py \
  tests/application/use_cases/test_inventory_status_lifecycle_and_backfill.py -q

cd backend && python -m pytest tests/api/test_capture_sessions_sprint2.py \
  tests/api/test_capture_sessions_sprint3.py tests/api/test_capture_sessions_materialize_phase4.py -q

cd backend && python -m pytest tests/api/test_aisles_v3_wiring.py -q

cd backend && ruff check tests/api/test_aisles_v3_wiring.py --fix && ruff check …
```

Frontend:

```bash
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm test -- --run tests/CreateInventoryDialog.creationFlow.test.tsx
cd frontend && npm run build
```

Mypy: not run as a dedicated targeted pass for this change set (project may use broader mypy config).

## 8. Risks / observations

- **Scripts / external callers** that POST `/api/v3/inventories` without `client_id` will now receive **422**; update any operational scripts accordingly.
- **409 aisle test** relies on a repository override; if dependency wiring changes, that test may need revisiting.

## 9. Recommendation for G3

Proceed to **G3 — Enforce `client_supplier_id` on new aisles** (write-path alignment with the client-oriented supplier model), keeping historical aisle rows and read nullability until any later schema phase explicitly changes them.

## 10. Out of scope (confirmed)

- NOT NULL on `inventories.client_id`, backfill, aisle supplier enforcement beyond existing rules, `inventory_visual_references`, `supplier_reference_images`, `supplier_prompt_configs`, prompt fallback, pipeline behavior, removal of inventory detail legacy warnings.
