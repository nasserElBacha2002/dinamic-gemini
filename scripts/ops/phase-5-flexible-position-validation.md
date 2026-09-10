# Phase 5 — Flexible position validation status (corrections)

```
PHASE_5_STATUS: IMPLEMENTED_WITH_BLOCKERS
SIGNATURE_POLICY: PROFILE_AWARE_VERSIONED (schema + resolver; settings = kill-switch/default)
CHANNEL_ISOLATION: VERIFIED (unit; Vision ON ≠ CODE_SCAN materialization)
ACCEPTED_WITHOUT_LOCATION: IMPOSSIBLE (AcceptPositionCoordinator contract)
SHADOW_SIGNATURE: PARTIAL (categories recorded; production window report not run)
SHADOW_PREEXISTENCE: PARTIAL (unit; live shadow report not run)
REVIEW_ASSOCIATION: PARTIAL (normalized code + complete_association when request_id exists)
SCOPED_ROLLOUT: PARTIAL (table + memory reader; SQL repo/API/wiring incomplete)
PREFLIGHT: SCRIPT_READY (not executed against live DB in this pass)
DEVICE_E2E: NOT_RUN
GLOBAL_ROLLOUT: DISABLED
READY_FOR_CONTROLLED_ROLLOUT: NO
```

## Corrections applied (this pass)

1. Channel isolation — removed shared `code_scan OR vision` gate; per-source flags on persister.
2. Accept never returns `accepted=True` with null `location_id`.
3. Migration `0111` — `signature_policy` on profiles + `position_flexible_capabilities`.
4. `NOT_APPLICABLE` + present signature → `SIGNATURE_NOT_ALLOWED_FOR_PROFILE`.
5. `resolve_effective_position_policy` (channel + capability ENFORCED).
6. Shadow divergence categories expanded (SIGNATURE, PREEXISTENCE, CLASSIFICATION, FORMAT, SCOPE, MATERIALIZATION_POSSIBLE).
7. Review persists normalized `corrected_position_code` (+ raw in after_json); completes association when materialization request_id exists.
8. Fail-closed settings for `POSITION_SIGNATURE_POLICY`; fail-closed profile policy normalize.
9. Strengthened preflight SQL (index filter, duplicates, ledger, capabilities).
10. Capability reader port + in-memory isolation helper (not yet wired to all productive callers).

## Residual P1 blockers (keep READY = NO)

| Blocker | Why |
|--------|-----|
| Migration 0111 not applied / preflight not run live | Schema guarantees unverified on target DB |
| Capability SQL reader + DI + admin path | Scoped ENFORCED cannot be operated end-to-end |
| Review durable association incomplete | No dedicated REVIEW receipt create + multi-reviewer protection + TX failure matrix |
| Shadow not integrated on all channels with live report | CODE_SCAN/Vision/Mobile/Import window evidence missing |
| Full suites not run | pytest full, mypy, frontend, mobile, Device E2E, assembleRelease, SQL multi-conn — **not executed** |
| Frontend profile signature_policy UI | Not updated in this pass |

## Controlled rollout thresholds (not yet measured)

Declare YES only after measured evidence for:

- Signature divergences below agreed %, invalid-signature reject rate = 100% of invalids
- Preexistence divergences understood; materialization error rate / recovery backlog
- Zero active identity duplicates; zero scope violations in shadow window
- Capability rollback test PASSED

## Validation executed this pass

- Targeted pytest (phase5 + bridge + migration smoke + preflight script): **34 passed**
- Ruff on touched modules: **passed**
- Full backend / frontend / mobile / Device E2E / live SQL preflight: **NOT RUN**
