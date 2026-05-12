# G3 — Enforce client_supplier_id on new aisles

## 1. Executive summary

**Final status:** `G3_READY_FOR_REVIEW`

Enforcement is implemented on all **write** paths that create aisles for inventories that have a client, including the capture-session **create-aisle-from-group** endpoint and the ingestion-session grouping UI. Historical rows remain readable with nullable `client_supplier_id` in API responses; database columns stay nullable until G4.x.

## 2. Scope implemented

- Backend: `CreateAisleUseCase` requires `client_supplier_id` when `inventory.client_id` is set; rejects legacy inventories without a client for **new** aisle creation; validates supplier existence and client ownership.
- API: `POST .../capture-sessions/.../groups/{group_id}/create-aisle` accepts `client_supplier_id` and forwards it to aisle creation (aligned with `POST .../aisles`).
- Frontend: `CreateAisleDialog` (inventory flows) and `ImportSessionGroupingPanel` capture-session “create aisle” dialog require supplier selection when the inventory has a client; Spanish copy via existing `dialogs.aisle.*` keys where applicable.
- Tests: backend aisle/create/capture-session tests and frontend grouping tests updated; mutation tests updated for `CreateAisleRequest` requiring supplier id.

## 3. Backend changes

- `CreateAisleFromCaptureGroupRequest` (`capture_schemas.py`): optional `client_supplier_id` with blank-string validation; conditional rules enforced in `CreateAisleUseCase`.
- `CreateAisleAndAssignCaptureSessionGroupUseCase`: passes `client_supplier_id` into `CreateAisleCommand`.
- Route `create_aisle_and_assign_capture_session_group_inventory_scope`: wires body field into use case.

## 4. Frontend changes

- `captureSessionsApi.createAisleFromCaptureSessionGroup`: sends `{ code, client_supplier_id }`.
- `useCreateAisleFromCaptureSessionGroup`: mutation variables include `client_supplier_id`.
- `ImportSessionGroupingPanel`: loads inventory (`useInventoryDetail`) and suppliers (`useClientSuppliers`); supplier select + disabled submit until supplier chosen; warning when inventory has no client.

## 5. Tests updated

- Backend: `test_capture_sessions_sprint2.py` (create-aisle-from-group includes supplier); `test_capture_session_group_g4.py` (unit test inventory + supplier fixtures).
- Frontend: `ImportSessionDetail.grouping.g4.test.tsx`, `ImportSessionDetail.grouping.test.tsx`, `ImportSessionGroupingPanel.g6-preview.test.tsx` (mocks for inventory + suppliers); `useMutations.phase6.test.tsx` (`client_supplier_id` on create-aisle mutation payloads).

## 6. Legacy compatibility retained

- Historical aisles with `client_supplier_id = NULL` remain listable/readable; response types stay null-safe.
- Historical inventories with `client_id = NULL` remain readable; **new** aisle creation returns a controlled domain/API error instead of creating drift.
- `aisles.client_supplier_id` and `inventories.client_id` remain nullable in the database; NOT NULL deferred to G4.1 / G4.2.

## 7. Validation results

| Command | Outcome |
| --- | --- |
| `cd backend && python -m pytest tests/api/test_capture_sessions_sprint2.py::test_create_aisle_from_group_flow tests/application/use_cases/test_capture_session_group_g4.py::test_create_aisle_and_assign_group -q` | Pass |
| `cd backend && ruff check src/api/schemas/capture_schemas.py src/application/use_cases/create_aisle_and_assign_capture_session_group.py src/api/routes/v3/capture_sessions.py` | Pass (no issues) |
| `cd frontend && npm run typecheck` | Pass |
| `cd frontend && npm run lint` | Pass |
| `cd frontend && npm test -- ImportSessionDetail.grouping.g4.test.tsx ImportSessionDetail.grouping.test.tsx ImportSessionGroupingPanel.g6-preview.test.tsx useMutations.phase6.test.tsx --run` | Pass (19 tests) |

## 8. Risks / observations

- Clients calling **only** `{ "code": "..." }` on `.../create-aisle` will receive validation/domain errors for client-oriented inventories; callers must send `client_supplier_id` (UI updated).
- Empty supplier list still blocks submit in grouping dialog (same product intent as main Create Aisle flow).

## 9. Recommendation for G4.1 / G4.2

- **G4.1:** Plan additive migration + application guarantees for `inventories.client_id` NOT NULL when historical backfill strategy is approved.
- **G4.2:** NOT NULL on `aisles.client_supplier_id` only after backfill and verification; keep API null-safe reads until deprecation window closes.

## 10. Out of scope (confirmed)

No DB NOT NULL, no backfill, no supplier reference images / prompt config / pipeline / `inventory_visual_references` changes.
