# Final DAST results

**Status:** `BLOCKED_BY_ENVIRONMENT`

## Preconditions checked

| Check | Result |
|-------|--------|
| `audit/lab/.env.lab` present | Yes |
| Lab SQL container attested healthy this session | No (docker inventory empty / not verified) |
| API on `127.0.0.1:18080` with `/lab/health` | Not verified |
| LLM providers mocked / fixture keys only | Assumed via lab template; not runtime-attested |
| Explicit LOCAL_ISOLATED_ONLY confirmation | Not obtained for an active stack |

## Decision

Per remediation policy, DAST was **not** executed against DEV/staging/production and was **not** started without a verified disposable lab. This is **not** a PASS.

## Compensating evidence

- Stage 2 JWT HTTP tenant isolation tests (company A/B, platform, parent/child, exports, bulk)
- SQL integration atomic soft-delete + scope tests

## Next step to unblock

1. `bash audit/lab/scripts/lab_preflight.sh && lab_up.sh && lab_bootstrap_schema.sh`
2. Seed + uvicorn on loopback
3. Attest `GET /lab/health`
4. Run passive → auth negative → A/B read-only → small exports → bounded mutations with cleanup
