# Result Context Contract (Phase 2)

## Precedence

1. **Explicit `job_id`** (query/body) — validated: exists, targets the aisle, actor may access inventory.
2. Else **`aisles.operational_job_id`** — validated the same way (no silent `jobs[0]`).
3. Else **legacy** — `positions.job_id IS NULL` only.

## Non-goals

- Never treat `jobs[0]`, newest `updated_at`, or first list row as operational SoT.
- Invalid operational pointer does **not** fall back to latest job; fail or use legacy only when contract allows.

## Single resolver

`src.application.services.result_context_resolver.ResultContextResolver`

Returns `ResolvedAisleResultContext` with `job_id_for_slice`, `source` (`explicit` | `operational` | `legacy` | `audit_all`), `read_mode`, `is_legacy`.

## Frontend

`resolveBrowseRunJobIds`: URL explicit → operational (display only) → null.
`passExplicitJobIdToApi` only when URL selects a listed job; otherwise omit `job_id` so backend owns SoT.
