# Final remediation summary (post-corrections)

**Status:** `REMEDIATION_PARTIALLY_COMPLETED`  
**UTC note:** 2026-09-15 close-out corrections

## Functional fixes this wave

1. Soft-delete: empty OUTPUT / still-active after write raises `InventorySoftDeleteConsistencyError` (no `not_found` after partial writes).
2. Fault injection on **second UPDATE** for standalone + UoW; both roll back.
3. Concurrent overlapping merge: root cause was invalid assertion (serialized dual success is valid) + deadlock mapped to `PositionMergeConflictError`; aisle UPDLOCK + HOLDLOCK + SERIALIZABLE UoW; **40/40** stable.
4. Honest findings: TEST-002 / extra tenant routes marked partial pending DAST; overall **PARTIALLY_COMPLETED**.
5. Gitleaks triaged; `.gitleaksignore` fixed; allowlists updated; recursive log removed.
6. Semgrep executed with **local** ruleset (registry blocked).

## Validation

- Backend full pytest: **5321 passed**
- Overlapping merge: **40/40 pass**
- Soft-delete SQL suite: green
- FE/mobile lint+typecheck+tests: green
- Official quality gate: see `final-quality-gate-results.txt` (may FAIL on Docker Gitleaks — not forced green)
