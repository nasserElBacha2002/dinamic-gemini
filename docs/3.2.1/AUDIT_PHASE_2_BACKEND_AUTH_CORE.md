# Audit: v3.2.1 Phase 2 — Backend auth core

## 1. Verdict

**Accepted with corrections.**

The Phase 2 implementation is largely correct, minimal, and within scope. Auth core behavior (password verification, JWT create/decode, login, `/auth/me`, error contract) is implemented and consistent with the Phase 1 contracts. A few concrete issues should be fixed before Phase 3; none are critical security or correctness blockers.

---

## 2. What is solid

- **Scope discipline:** No v3 business routes use `get_current_admin`; no frontend or route-protection logic was added. Phase 2 boundaries are respected.
- **Password verification:** `verify_password` uses passlib `CryptContext` with bcrypt/pbkdf2_sha256, no plaintext comparison, and fails closed on bad hash or empty input (returns `False`). No credentials in logs.
- **Token design:** JWT with HS256, minimal claims (`sub`, `username`, `role`, `iat`, `exp`), secret from config, expiration enforced by `jwt.decode`. Invalid/expired tokens raise and are mapped to 401 with stable contract.
- **Auth error contract:** `AuthHttpError` plus FastAPI exception handler ensure all auth failures return `{"error": {"code": "...", "message": "..."}}`; no accidental `{"detail": ...}` for auth paths.
- **Login behavior:** Username compared to config; password verified via hash; single generic "Invalid credentials." on failure; no distinction between wrong username vs wrong password.
- **Current-admin resolution:** `get_current_admin` parses `Authorization: Bearer <token>`, validates token, validates claims (`sub == "admin"`, `username`/`role` present and string), and returns `AuthUser`. Reusable for Phase 3.
- **Dependencies:** passlib, bcrypt, PyJWT are appropriate and integrated correctly; config remains externalized.

---

## 3. Findings

### Critical

*None.*

### Major

**1. Login can raise 500 when `AUTH_TOKEN_SECRET` is missing (misconfiguration).**

- **Files:** `backend/src/auth/service.py` (`build_login_response`), `backend/src/auth/security.py` (`create_access_token`).
- **Issue:** After successful `authenticate_admin`, `build_login_response` calls `create_access_token(..., secret=s.token_secret)`. If `token_secret` is empty, `create_access_token` raises `ValueError("auth token secret is missing")`, which is not caught by the auth exception handler, so FastAPI returns 500 and a generic error body.
- **Why it matters:** In misconfigured environments (e.g. username/hash set but secret forgotten), operators see 500 instead of a clear configuration error or a consistent 401.
- **Recommendation:** Before calling `create_access_token` in `build_login_response`, check `if not s.token_secret` and raise `AuthHttpError(status_code=500, error=AuthError(code="SERVER_ERROR", message="Auth is misconfigured."))` or document that empty secret is invalid and handle it in one place (e.g. in `build_login_response`) so the response is always JSON and predictable. Prefer 503 or 500 with a non-leaking message over unhandled ValueError.

**2. Missing test for `/auth/me` success with valid token.**

- **Files:** `backend/tests/auth/test_auth_api.py`.
- **Issue:** Tests cover login success, login failure, and `/auth/me` for missing/invalid/expired token. There is no test that logs in, then calls `GET /auth/me` with the returned token and asserts 200 and the current-user payload.
- **Why it matters:** The happy path for `/auth/me` is not asserted; a regression could go unnoticed.
- **Recommendation:** Add e.g. `test_auth_me_success_with_valid_token`: POST `/auth/login` with valid credentials, extract `access_token`, GET `/auth/me` with `Authorization: Bearer <token>`, assert status 200 and body `{"id":"admin","username":"admin","role":"administrator"}`.

### Minor

**3. Redundant `int()` in `build_login_response`.**

- **File:** `backend/src/auth/service.py`, line 65: `expires_in=int(s.token_expires_minutes) * 60`.
- **Issue:** `AuthSettings.token_expires_minutes` is already `int` from config; `int()` is redundant.
- **Recommendation:** Use `s.token_expires_minutes * 60` for clarity (or keep for defensive coding; low priority).

**4. Stale 501 in OpenAPI for auth routes.**

- **File:** `backend/src/auth/routes.py`: `responses={..., status.HTTP_501_NOT_IMPLEMENTED: {"model": AuthErrorResponse}}` on both routes.
- **Issue:** Phase 2 implements both endpoints; 501 is no longer returned. OpenAPI still advertises 501, which is misleading.
- **Recommendation:** Remove `HTTP_501_NOT_IMPLEMENTED` from the `responses` dict for `/auth/login` and `/auth/me`.

**5. test_auth_api fixture uses deprecated passlib `scheme=`.**

- **File:** `backend/tests/auth/test_auth_api.py`, line 24: `_PWD_CONTEXT.hash("correct-password", scheme="pbkdf2_sha256")`.
- **Issue:** Passlib deprecation warning: `scheme` keyword will be removed in 2.0.
- **Recommendation:** Use a context that only has `pbkdf2_sha256` (e.g. `CryptContext(schemes=["pbkdf2_sha256"])`) so the default hash is pbkdf2, and call `hash("correct-password")` without `scheme=`. Alternatively ignore the warning for now and add a TODO.

---

## 4. Scope compliance

- **No global protection of business routes:** Confirmed. `get_current_admin` is used only by `GET /auth/me`. v3 routers do not depend on it.
- **No frontend work:** No changes under `frontend/`.
- **No extra auth features:** No refresh tokens, no user DB, no RBAC, no multi-user logic.
- **No overengineering of identity:** Single admin principal with `id`, `username`, `role` only.
- **No unnecessary refactors:** Only auth-related files and server exception handler were touched.

**Conclusion:** Phase 2 stays within the defined scope.

---

## 5. Test assessment

- **Security helpers:** `test_verify_password_valid_and_invalid` and `test_token_roundtrip_and_expiration` meaningfully validate verification and JWT create/decode/expiration. Good.
- **API behavior:** Login success, login invalid credentials, `/auth/me` missing/invalid/expired token are covered and assert status and body shape. Good.
- **Gaps:** (1) No test for `/auth/me` success with a token obtained from login. (2) No test for login when config has username/hash but empty token secret (currently would 500; after recommended fix, could assert 500/503 and error shape). (3) No test for malformed or wrong-prefix `Authorization` header (e.g. `Basic ...` or `Bearer` with no space). (4) Optional: test that invalid JSON or wrong content-type on login returns 422, not 401.

**Conclusion:** Tests are sufficient to validate the main flows and failure modes. Adding the `/auth/me` success case and, if you fix the empty-secret case, a test for that, would strengthen the suite.

---

## 6. Go / No-Go for Phase 3

**Go for Phase 3** after addressing:

- **Major (recommended before Phase 3):** Handle missing `AUTH_TOKEN_SECRET` in `build_login_response` so misconfiguration yields a controlled 500/503 and JSON body instead of an uncaught `ValueError`. Add at least one test for `/auth/me` success with valid token.

**Optional (can be done in Phase 3 or later):** Remove 501 from auth route OpenAPI, trim redundant `int()` in `build_login_response`, and reduce passlib deprecation in tests.

---

## 7. If corrections are needed

**Correction plan (minimal):**

1. **Empty token secret (Major #1)**  
   In `backend/src/auth/service.py`, at the start of `build_login_response`, add:
   ```python
   if not (s.token_secret or "").strip():
       raise AuthHttpError(
           status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
           error=AuthError(code="SERVER_ERROR", message="Auth is misconfigured."),
       )
   ```
   (Use a suitable code; 503 is acceptable for “server misconfiguration.”) Ensure `AuthHttpError` and `status` are imported in `service.py` (today they are not—so you’d add the import and the check, and use an exception that the server’s exception handler already turns into JSON; `AuthHttpError` is the right choice.) So: in `service.py` import `AuthHttpError`, `AuthError`, and `status` from `fastapi` and `src.auth.errors` / `src.auth.schemas`, then add the check and raise `AuthHttpError` so the global handler returns the stable `error` envelope.

2. **Test for `/auth/me` success (Major #2)**  
   In `backend/tests/auth/test_auth_api.py`, add:
   ```python
   def test_auth_me_success_with_valid_token():
       client = TestClient(app)
       login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
       assert login_r.status_code == 200
       token = login_r.json()["access_token"]
       me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
       assert me_r.status_code == 200
       assert me_r.json() == {"id": "admin", "username": "admin", "role": "administrator"}
   ```

3. **Minor #4 (OpenAPI):** In `backend/src/auth/routes.py`, remove the `status.HTTP_501_NOT_IMPLEMENTED` entry from the `responses` dict for both `/login` and `/me`.

4. **Minor #3:** In `service.py`, use `s.token_expires_minutes * 60` unless you prefer defensive `int()`.

5. **Minor #5:** In test_auth_api, consider a `CryptContext(schemes=["pbkdf2_sha256"])` for the fixture hash so `scheme=` can be dropped (or leave as-is and accept the deprecation for now).

No other code changes are required for the audit verdict.
