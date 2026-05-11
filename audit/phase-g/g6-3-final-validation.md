# G6.3 — Prompt fallback final validation

## 1. Executive summary

**Status: `PHASE_G6_CLOSED_READY_FOR_G7`**

Missing supplier prompt configuration for a fully scoped client-oriented aisle now **blocks** v3 processing by default, with **explicit** job failure text and optional **emergency** env-based fallback. Frontend surfaces **Spanish** warnings and trace translations. SQL migration/runtime DB checks were **not** re-validated in this workspace (timeout); operator verification remains recommended.

## 2. Backend validation

- Resolver unit tests updated for **error vs fallback**.
- Broad pytest filter **`supplier_prompt or effective_prompt or fallback`** — **pass** (see raw log).

## 3. Frontend validation

- **typecheck / lint / build / supplier detail tests** — **pass**.

## 4. Prompt config success path

- Unchanged when **`_resolve_active_with_precedence`** returns an active row; **`effective_prompt_hash`** still computed on composed text.

## 5. Missing config blocked / fallback path

- **Default:** `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG` → **`resolution_status=error`** → executor fails before pipeline.
- **Emergency:** `V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK=true` → **`fallback`** path preserved.

## 6. Metadata validation

- Historical logs retaining **`fallback_used`** / **`effective_prompt`** shapes remain valid for succeeded runs.
- Protected contract composition unchanged.

## 7. Provider / adapter regression coverage

- Existing hybrid / traceability tests executed under filtered pytest; no adapter edits in G6.

## 8. Remaining observations

- Production should keep emergency env **false** unless ops approves.

## 9. Recommendation for G7

Proceed to **Phase G closure audit** (`g7-0-final-audit.md`) and final report.
