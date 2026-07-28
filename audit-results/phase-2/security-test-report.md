# Security Test Report (Phase 2)

## Client scope / IDOR

- Cross-client upload rejected before storage write.
- Cross-client list/delete rejected (`InventoryNotFoundError` → HTTP 404 policy).
- Platform admin may cross client.

## Pre-spool HTTP auth (Phase 2 correction)

New suite: `backend/tests/api/test_capture_session_upload_prespool_auth_phase2.py` (9 tests,
real FastAPI `TestClient`, in-memory repos, real dependency code — only `get_current_admin` and
repositories/storage are overridden).

- Capture session staging upload cross-hierarchy denials (session in another inventory, aisle in
  another inventory, session/aisle mismatch, nonexistent session, cross-client company actor) all
  return the mapped 404 with **zero** multipart-spool calls, zero artifact-storage writes, and
  zero persisted `CaptureSessionItem` rows.
  A platform-actor positive control confirms the spool and use case *do* run (count == 1) for a
  valid request, so the "zero calls" assertions above are meaningful rather than vacuously true.
- Aisle asset upload cross-client denial is also zero-spool. Aisle-belongs-to-another-inventory
  is caught only after the (defense-in-depth) use-case-level aisle check — see the matrix doc for
  detail — so storage/DB writes are still zero but the multipart spool step itself runs once.
  A platform-actor positive control mirrors the capture-session one.

## Result SoT

- Cross-contract: operational B preferred when jobs list would surface A first.
- Resolver unit suite + list positions suite.

## Memory policy

- Production + MEMORY_ONLY forbidden.
- Production + V3_ALLOW override ignored.
- Unknown env requires SQL / rejects fallback.
