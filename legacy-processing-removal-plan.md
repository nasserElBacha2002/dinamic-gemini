# Legacy processing removal plan (Phase 8)

## Completed in this PR (Etapas A–C)

- [x] A — Inventory + classification docs
- [x] B — Block new LEGACY config writes and explicit job overrides
- [x] C — Hide legacy process options; conditional observability; remove duplicate scan menu entry
- [x] Presentation mapper (frontend)
- [x] Temporary in-process metrics counters
- [x] Stage label fix for INTERNAL_OCR

## Etapa D — Config migration (next)

1. Read-only SQL report (clients / inventories / aisles / recent jobs with LEGACY).
2. Tenant policy mapping (`LEGACY_LLM` → `INTERNAL_OCR` or inherit).
3. Dry-run + reversible UPDATE scripts (no DROP).
4. Change system default away from `LEGACY_LLM` only after tenant soak.

## Etapa E — Backend path removal

1. Confirm zero traffic to explicit LEGACY overrides (metrics).
2. Deprecate `/code-scans/run` if CODE_SCAN jobs fully replace auxiliary pyzbar runs (evidence endpoints may stay).
3. Remove dead FE hooks only after zero menu/deep-link usage.

## Etapa F — Flags / DB cleanup

1. Observation window ≥ soak period.
2. Remove temporary metrics or promote to Prometheus.
3. Additive deprecation columns only first; DROP later with separate approval.

## Rollback (current)

Revert this change set; feature flags for CODE_SCAN/INTERNAL_OCR remain the primary worker rollback levers.
