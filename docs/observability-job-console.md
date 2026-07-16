# Observability — job artifacts, retry chain, logs, timeline

## Roles and scope

- `platform_admin` (legacy JWT role `administrator` accepted as alias): may omit `client_id` (global).
- `company_admin` / `operator`: **require** `client_id` (fail closed on request).
- Env principals: unbound → `platform_admin`; `AUTH_*_CLIENT_ID` set → `company_admin`.

## Capabilities (backend enforced)

Applied via `require_observability_capability(...)` on Observability + legacy log/auditability/cancel/retry/recovery routes.

## Inputs

`job_source_assets` snapshot (migration `0045`) written when pipeline inputs resolve. Legacy jobs without snapshot → `inputs_legacy_unverified` (no aisle-wide asset invention).

## Log pagination

`GET .../execution-log/page` uses incremental JSONL byte-offset cursors (`pagination_mode=incremental`). Invalid / filter-mismatched cursor → `400 INVALID_CURSOR`. Desc order uses capped fallback (`legacy_capped`).

## Residual

- Physical move of handlers from `aisles.py` → `job_observability.py` (module stub present).
- Structured timeline emission at every pipeline frontier (derived events no longer invent terminal states from free text).
- Full HTTP matrix + FE vitest race tests + container PR gate evidence.
