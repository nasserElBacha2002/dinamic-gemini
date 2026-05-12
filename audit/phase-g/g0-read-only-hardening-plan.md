# G0 — Read-only audit and hardening plan

**Date:** 2026-05-11  
**Scope:** Phase G — Hardening / cleanup legacy (subphase **G0** only — documentation and read-only findings).  
**Method:** Static inspection of `backend/src`, `frontend/src`, `backend/src/database/schema.sql`, selected migrations and tests. No runtime DB connection, no code or schema mutations.

---

## 1. Executive summary

The codebase is **already bifurcated** between a **legacy-optional** path (inventories and aisles may omit `client_id` / `client_supplier_id`) and a **client-oriented** path (supplier reference images, supplier prompt configs, ownership validation when IDs are present). The API and UI **still allow** creating inventories without a client and aisles without a supplier when the inventory has no client, matching explicit tests and schema **NULL** columns.

**Canonical operational references** for v3 aisle processing are **`supplier_reference_images`** resolved through `AisleAnalysisContextBuilder` and `SupplierReferenceImageResolver`; legacy **`inventory_visual_references`** is migration-bound for removal (`0029_drop_inventory_visual_references.sql`) and is not part of the active v3 API surface reviewed here.

**Job-level relational columns** for `client_id` / `client_supplier_id` / `effective_prompt_hash` were **not** observed on `inventory_jobs` in `schema.sql`; traceability for prompts and references is primarily in **`result_json`**, **`payload_json`**, and **`job_events.payload`**, plus execution-log summaries (hashes / allowlisted `effective_prompt` keys per `prompt_traceability.py`).

**Recommendation:** **`READY_FOR_G1_WITH_OBSERVATIONS`** — safe to start **G1 drift metrics** (read-only counts, JSON path sampling) while treating **NOT NULL migrations (G4)** and **legacy table removal (G5)** as later slices with explicit backfill and downtime/rollback planning.

---

## 2. Current architecture confirmation

| Layer | Client / supplier model |
|-------|-------------------------|
| **DB** | `inventories.client_id` **NULL** + FK to `clients`; `aisles.client_supplier_id` **NULL** + FK to `client_suppliers`; `supplier_reference_images`, `supplier_prompt_configs` tied to `client_suppliers`. |
| **API** | `CreateInventoryRequest.client_id` optional; `CreateAisleRequest.client_supplier_id` optional; when supplier provided, `CreateAisleUseCase` enforces inventory has client and supplier belongs to that client. |
| **Pipeline** | `SupplierPromptResolver` + `SupplierReferenceImageResolver` / builder produce explicit **fallback** statuses when client or supplier missing or no active config/images. |
| **Frontend** | `CreateInventoryDialog` can omit `client_id`; `CreateAisleDialog` requires supplier only when `inventoryClientId` is set; inventory detail shows legacy warning when no client. |

---

## 3. Inventory client ownership findings

| Question | Finding |
|----------|---------|
| Does `CreateInventoryRequest` require `client_id`? | **No.** Optional `str \| None`, documented as preserving legacy behavior (`inventory_schemas.py`). |
| Backend validation? | If `client_id` is non-null, `CreateInventoryUseCase` checks `ClientRepository.get_by_id` → `ClientNotFoundError` if missing (`test_create_inventory.py`). |
| Frontend create without client? | **Yes.** `CreateInventoryDialog` sends `client_id` only when selector non-empty; `MenuItem value=""` = “Sin cliente (legado)” (`CreateInventoryDialog.tsx`). |
| Historical NULL `client_id`? | Supported: column nullable; UI warning on inventory detail (`InventoryDetail.tsx` + `inventory.legacy_no_client_warning`). |
| API null-safe? | Response models use `client_id: str \| None = None` (`InventoryResponse`, list rows). |
| Tests | `test_create_inventory_with_explicit_null_client_id_keeps_legacy_behavior`, `...valid_client_id...`, `...invalid_client_id_raises...` |
| Seeds/scripts | `backfill_legacy_client_supplier_defaults.py` exists for migration-style fixes; review before G4. |

---

## 4. Aisle supplier ownership findings

| Question | Finding |
|----------|---------|
| `CreateAisleRequest` require `client_supplier_id`? | **No** — optional (`aisle_schemas.py`). |
| Backend validation when set? | `CreateAisleUseCase`: supplier exists; if inventory has **no** `client_id`, raises `InventoryClientRequiredForSupplierError`; if `supplier.client_id != inventory.client_id`, raises `ClientSupplierClientMismatchError`. |
| Frontend without supplier? | If inventory **has no** client, supplier UI skipped and request omits `client_supplier_id` (`CreateAisleDialog.tsx`). If inventory **has** client, supplier required when suppliers list non-empty. |
| Historical NULL `client_supplier_id`? | Supported at DB and API response level. |
| Tests | Search `test_create_aisle` under `backend/tests` (use case + API wiring). |

---

## 5. Supplier reference images vs legacy visual references

| Question | Finding |
|----------|---------|
| Canonical store | **`supplier_reference_images`** + resolver/builder pipeline path (`AisleAnalysisContextBuilder`, `v3_process_aisle_pipeline_runner`). |
| Active API for `inventory_visual_references`? | **Not found** in `backend/src/api` quick scan; table is legacy / migration-target (`0029` drops when empty). |
| Pipeline fallback to inventory table? | Operational path reviewed uses **supplier** repo list; inventory-without-client sets resolution status to `fallback_inventory_without_client` (no DB read of legacy inventory references in builder snippet). |
| Deprecate legacy table? | **G5 candidate** — precondition: confirm table empty in all environments; migration 0029 already encodes drop-when-empty policy. |

---

## 6. Supplier prompt config and fallback findings

| Question | Finding |
|----------|---------|
| Source for editable instructions | `supplier_prompt_configs` (+ versions, active row per scope) via repositories and v3 client routes. |
| Active config per scope | Yes — unique indexes in schema / migrations for scope + version + one active. |
| No active config? | `SupplierPromptResolver` returns `fallback_used` with reasons e.g. `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`, `INVENTORY_WITHOUT_CLIENT`, `AISLE_WITHOUT_CLIENT_SUPPLIER`. |
| `fallback_used` persisted? | In **composition / execution log summaries** (see `EFFECTIVE_PROMPT_EXECUTION_LOG_KEYS`); not a dedicated first-class column on `inventory_jobs` in reviewed schema. |
| Protected blocks | `protected_prompt_contract_key` / `version` from `effective_prompt_composer.py` + traceability module; versioned constants. |
| `effective_prompt_hash` | Part of allowlisted execution-log `effective_prompt` projection (`prompt_traceability.py`). |
| Reduce fallback (G6) | Requires product policy: e.g. fail-closed vs continue with explicit operator-visible fallback; must align with tests in `supplier_prompt_resolver` / pipeline. |

---

## 7. Pipeline execution metadata findings

| Field (spec) | Finding (high level) |
|----------------|----------------------|
| `client_id` | On **inventory** entity and propagated into analysis metadata / resolution objects; **not** a dedicated column on `inventory_jobs` in `schema.sql`. |
| `client_supplier_id` | On **aisle** + embedded in context metadata (`aisle_analysis_context_builder`). |
| `supplier_prompt_config_id` / `_version` | In `SupplierPromptResolution` and effective prompt / execution log allowlist. |
| `protected_template_key` (spec wording) | Implemented as **`protected_prompt_contract_key`** (+ `_version`) in composer/traceability. |
| `effective_prompt_hash` | Present in allowlisted keys. |
| `reference_images_used` | **No exact key** under that name found via `rg`; use **`supplier_reference_image_count`** + `supplier_reference_resolution_status` / `reference_source` in metadata. |
| `fallback_used` | On supplier prompt resolution + pallet-level `fallback_used` column in **`pallet_results`** (legacy CV path) — distinguish domains. |
| `provider_name` / `model_name` | Columns on `inventory_jobs` (`schema.sql`). |

**Gap:** Uniform SQL reporting across all fields may require **JSON_VALUE** probes on `inventory_jobs.result_json` — paths must be validated per environment (see `g0-db-checks.sql` comments).

---

## 8. Frontend legacy exposure findings

| Surface | Finding |
|---------|---------|
| Create inventory without client | **Allowed** (explicit empty client option + omit field in POST body). |
| Create aisle without supplier | **Allowed** when inventory has no client; **required** when inventory has client and suppliers exist. |
| Legacy inventory-level reference UI | **Removed** from inventory detail in Phase F context (per prior closure); supplier management on supplier detail tabs. |
| Warnings | Legacy no-client inventory warning present. |
| English / raw keys | Phase F audit noted residual `es` JSON debt; not re-scanned exhaustively in G0. |

---

## 9. Database readiness checklist

See **`audit/raw/phase-g/g0-db-checks.sql`** for SELECT-only probes (NULL counts, orphan checks, inactive client/supplier joins, optional JSON probes).

---

## 10. Validation command inventory

See **`audit/raw/phase-g/g0-validation-commands.txt`**.

---

## 11. Risks and blockers

| Risk | Severity | Mitigation |
|------|----------|------------|
| Forcing NOT NULL on inventories/aisles while NULL rows exist | **High** | G4 requires backfill + application enforcement order (G2/G3 first). |
| Dropping `inventory_visual_references` while non-empty in any env | **High** | Run section 15 of SQL checklist; use 0029 preconditions. |
| JSON path drift in `result_json` for metrics | **Medium** | G1: sample rows, document canonical paths per `job_type`. |
| Operators rely on “no client” inventories | **Medium** | Product decision before G2/G4. |

**No blocker** identified for starting **read-only drift metrics (G1)**.

---

## 12. Recommended Phase G execution plan

### G1 — Drift metrics and read-only validation script

- **Objective:** Quantify NULL `client_id` / NULL `client_supplier_id`, orphan ownership, JSON presence of `fallback_used` / `effective_prompt_hash`, supplier table row counts.
- **Preconditions:** Read-only DB access; SQL from `g0-db-checks.sql`.
- **Files later:** New script under `backend/scripts/` or `tools/` (not in G0).
- **Risks:** Misleading counts if JSON paths wrong.
- **Tests:** N/A (tooling); optional snapshot tests on fixture DB.
- **Rollback:** N/A (read-only).
- **DoD:** Dashboard or markdown report checked in under `audit/phase-g/`.

### G2 — Enforce `client_id` on **new** inventories

- **Objective:** API + UI require client for creates; keep NULL for legacy rows until G4.
- **Preconditions:** Product sign-off; frontend dialog default; backend 400 on missing client.
- **Files later:** `inventory_schemas.py`, `create_inventory.py`, `inventories.py`, `CreateInventoryDialog.tsx`, tests.
- **Risks:** Breaks integrations still posting without client.
- **Rollback:** Feature flag or revert API change.
- **DoD:** Contract tests + UI tests updated.

### G3 — Enforce `client_supplier_id` on **new** aisles (when inventory has client)

- **Objective:** Align with G2; reject aisle create without supplier if inventory.client_id set.
- **Preconditions:** G2 stable.
- **Files later:** `aisle_schemas.py`, `create_aisle.py`, `CreateAisleDialog.tsx`, tests.
- **Risks:** Same as G2 for automated aisle creators.
- **DoD:** Tests for 400 paths.

### G4.1 — `inventories.client_id` NOT NULL readiness / migration

- **Objective:** Backfill NULLs → synthetic or real clients; then NOT NULL + retain FK.
- **Preconditions:** G2 live; drift counts zero or backfilled.
- **Files later:** New migration SQL, optional data script, repositories.
- **Risks:** Long locks on large tables.
- **Rollback:** Migration downgrade script (if supported).
- **DoD:** Migration test + staging verification.

### G4.2 — `aisles.client_supplier_id` NOT NULL readiness / migration

- **Objective:** Same pattern tied to inventory client.
- **Preconditions:** G3 + G4.1.
- **Files later:** Migration SQL, `create_aisle`, domain defaults.
- **Risks:** Aisles on legacy inventories must be resolved first.
- **DoD:** Same as G4.1.

### G5 — Deprecate `inventory_visual_references`

- **Objective:** Execute 0029 policy everywhere; remove dead code paths if any remain.
- **Preconditions:** Table empty in all envs; pipeline confirmed not to read table.
- **Files later:** Migrations, scripts, docs.
- **Risks:** Historical audit need for old rows.
- **DoD:** Table absent; grep clean in `backend/src`.

### G6 — Reduce prompt fallback

- **Objective:** Policy: stricter failure vs explicit operator override; tighten logging.
- **Preconditions:** G4 stable; observability verified for operators.
- **Files later:** `supplier_prompt_resolver.py`, pipeline, FE copy.
- **Risks:** Increased failed jobs.
- **DoD:** Tests + observability review.

### G7 — Phase G final review

- **Objective:** Sign-off checklist, update `.env.example` if logging flags change, archive audits.
- **DoD:** Single closure doc + green CI.

---

## 13. G1 readiness decision

**`READY_FOR_G1_WITH_OBSERVATIONS`**

Observations: legacy NULLs are intentional today; JSON metadata paths need empirical sampling before automated dashboards.

---

## 14. Final recommendation

Proceed to **G1 — drift metrics** using `audit/raw/phase-g/g0-db-checks.sql` and extend with JSON sampling queries after inspecting live `result_json` samples.

**Suggested next prompt (G1):**  
“Implement G1 read-only drift report: script + documented queries for NULL client/supplier, orphan FKs, `inventory_jobs.result_json` keys (`fallback_used`, `effective_prompt_hash`, `prompt_composition`), and supplier_reference_images vs dropped legacy table; output markdown under `audit/phase-g/`; no schema or API changes.”
