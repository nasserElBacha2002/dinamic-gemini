# E2 — SupplierPromptResolver

**Date:** 2026-05-11  
**Roadmap:** Phase E — Prompt Composer + Pipeline Integration (Client-Oriented Redesign)

---

## 1. Executive summary

E2 introduces an **application-layer** `SupplierPromptResolver` that, given `inventory_id`, `aisle_id`, and optional `provider_name` / `model_name`, loads inventory and aisle context, validates that the aisle’s `client_supplier` belongs to the inventory’s `client_id`, and selects the **active** `supplier_prompt_config` for that supplier using a fixed **three-tier precedence** within `client_supplier_id`. It returns a **frozen** `SupplierPromptResolution` with `resolution_status` of `resolved`, `fallback`, or `error`, plus stable `fallback_reason` / `error_code` strings for auditing.

**No** changes were made to hybrid prompt text, `LLMRequest`, adapters, normalization, parsing, database schema, or pipeline wiring.

---

## 2. Resolver responsibilities

- Load inventory by id; read `client_id`.
- Load aisle by id; verify `aisle.inventory_id == inventory_id`.
- Read `aisle.client_supplier_id`; load `ClientSupplier` and verify `supplier.client_id == inventory.client_id`.
- Normalize provider (trim, lower) and model (trim; empty → `None`). Reject **model without provider** as `INVALID_SCOPE_INPUT`.
- Resolve active config via `SupplierPromptConfigRepository.get_active_by_scope` in precedence order (see below).
- Return structured result only; **do not** call LLMs or mutate prompts.

---

## 3. Resolver inputs

| Input | Role |
|--------|------|
| `inventory_id` | Inventory row lookup |
| `aisle_id` | Aisle row lookup |
| `provider_name` | Optional; normalized to lowercase or `None` |
| `model_name` | Optional; trimmed or `None` |

---

## 4. Resolver output shape

`SupplierPromptResolution` (`backend/src/application/services/supplier_prompt_resolver.py`):

- Identifiers: `inventory_id`, `aisle_id`, `client_id`, `client_supplier_id` (when known from successful path segments).
- Scope echo: `provider_name`, `model_name` (normalized values used for resolution).
- Config: `supplier_prompt_config_id`, `supplier_prompt_config_version`, `editable_instructions` (from `instructions_text` when resolved).
- Flags: `fallback_used`, `fallback_reason`, `resolution_status` (`resolved` \| `fallback` \| `error`), `warnings` (tuple; reserved), `error_code` when `error`.

---

## 5. Config precedence (within one `client_supplier_id`)

1. **Exact provider + exact model** — when both normalized values are non-null: `get_active_by_scope(sid, provider, model)`.
2. **Provider default** — `get_active_by_scope(sid, provider, None)` (DB row with `model_name` null).
3. **Supplier-wide default** — `get_active_by_scope(sid, None, None)` (both null in DB).

Never queries outside the aisle’s `client_supplier_id`. Reuses the repository port; precedence is implemented in the resolver to avoid duplicating SQL-specific ordering if repositories differ.

---

## 6. Fallback policy

| Condition | `resolution_status` | `fallback_used` | `fallback_reason` |
|-----------|---------------------|-----------------|-------------------|
| Inventory has no `client_id` | `fallback` | `true` | `INVENTORY_WITHOUT_CLIENT` |
| Aisle has no `client_supplier_id` | `fallback` | `true` | `AISLE_WITHOUT_CLIENT_SUPPLIER` |
| No active config for scope | `fallback` | `true` | `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG` |

---

## 7. Ownership validation

When `client_supplier_id` is present, the resolver loads `ClientSupplier` and requires `supplier.client_id == str(inventory.client_id).strip()`. On mismatch: `resolution_status == "error"`, `error_code == "CLIENT_SUPPLIER_OWNERSHIP_MISMATCH"`, `fallback_used == false` (data integrity, not legacy fallback).

Additional **error** outcomes (not fallbacks): inventory not found, aisle not found, aisle/inventory id mismatch, supplier id not found, invalid scope (model set, provider empty).

---

## 8. Files changed

| File | Change |
|------|--------|
| `backend/src/application/services/supplier_prompt_resolver.py` | New resolver + resolution dataclass + reason/error constants |
| `backend/tests/application/test_supplier_prompt_resolver.py` | Unit tests (memory repos) |
| `audit/phase-e/e2-supplier-prompt-resolver.md` | This document |
| `audit/phase-e/e2-closure.md` | Phase closure |

---

## 9. Tests added

`backend/tests/application/test_supplier_prompt_resolver.py` covers:

- Exact provider+model match vs broader scopes.
- Fallback chain: model-specific → provider default → all-provider default.
- Fallbacks: no `client_id`, no `client_supplier_id`, no active config.
- Errors: ownership mismatch, aisle/inventory mismatch, missing inventory/aisle/supplier, invalid scope (model without provider).
- Inactive configs ignored (via repository `is_active`).
- Provider casing/whitespace normalization.
- Cross–`client_supplier_id` isolation.

---

## 10. Runtime behavior impact

**None** on live LLM prompts or pipeline execution. The resolver is **not** wired into `v3_job_executor`, hybrid pipeline, or prompt composers in this phase.

---

## 11. Remaining risks

- **E3/E4 ordering:** When `editable_instructions` are merged, OpenAI vs Gemini ordering must be re-validated against the protected contract (per E1 notes).
- **Repository parity:** SQL `get_active_by_scope` must remain consistent with memory semantics for the three scopes; resolver assumes exact key match per call (no global search).

---

## 12. E2 final status recommendation

`PHASE_E2_CLOSED_READY_FOR_E3` — resolver is isolated, tested, and ready for **E3 — EffectivePromptComposer** to consume `SupplierPromptResolution` without changing E2 boundaries in this commit.
