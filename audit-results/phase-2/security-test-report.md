# Security Test Report (Phase 2)

## Client scope / IDOR

- Cross-client upload rejected before storage write.
- Cross-client list/delete rejected (`InventoryNotFoundError` → HTTP 404 policy).
- Platform admin may cross client.

## Result SoT

- Cross-contract: operational B preferred when jobs list would surface A first.
- Resolver unit suite + list positions suite.

## Memory policy

- Production + MEMORY_ONLY forbidden.
- Production + V3_ALLOW override ignored.
- Unknown env requires SQL / rejects fallback.
