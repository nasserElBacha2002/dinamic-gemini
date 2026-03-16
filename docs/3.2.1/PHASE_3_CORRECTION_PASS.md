# v3.2.1 Phase 3 — Backend route protection: correction pass

## A. Summary of corrections applied

### 1. V3 router module structure
**Verified.** The main v3 router file (`backend/src/api/routes/v3/router.py`) was audited; no structural issues were found:
- One module docstring (describes v3 API and Phase 3 auth).
- One import block: `fastapi`, `src.auth.dependencies.get_current_admin`, local sub-routers.
- One `router = APIRouter(...)` with `prefix`, `tags`, and `dependencies=[Depends(get_current_admin)]`.
- Five `include_router` calls (inventories, aisles, assets, positions, reviews).
- No duplicate or dead code; no imports inside docstrings.

**No changes made** to the router file.

### 2. Route surface audit
**Verified.** Backend route tree:
- **App** mounts: `v3_router` (no app-level prefix), `auth_router` (prefix `/auth`). Health at `GET /health`.
- **V3 router** has prefix `/api/v3/inventories` and includes all five sub-routers with no additional prefix. Every v3 endpoint is therefore under this single router and inherits the router-level `get_current_admin` dependency.
- **No v3 business routes exist outside** the protected router; there are no other v3 mounts or v3 routes on the app.
- **Conclusion:** All active v3 operational routes are covered by the router-level dependency. No route-surface fixes were required.

### 3. Public vs protected boundary
**Verified.** Matches the intended boundary:
- **Public:** `GET /health`, `POST /auth/login`.
- **Protected:** `GET /auth/me` (route-level `Depends(get_current_admin)`), and all routes under `/api/v3/inventories/*` (router-level dependency).
- No active v3 endpoint is public; no public endpoint was incorrectly protected.

**No changes made** to the boundary.

### 4. Unauthorized behavior (stable auth contract)
**Verified.** `get_current_admin` raises `AuthHttpError` with `AuthError(code="UNAUTHORIZED", message="Authentication required.")`. The app’s `AuthHttpError` exception handler returns `exc.to_response_body()`, which produces:
```json
{"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}
```
Protected business routes do not use FastAPI’s default `{"detail": "..."}` for auth failures. Existing tests assert this envelope; one additional test was added to cover POST on a protected route.

**No contract fixes required.**

### 5. Tests
**Updated.** One test added:
- `test_v3_post_inventories_missing_token_unauthorized`: POST `/api/v3/inventories` without token → 401 and the stable auth envelope. Confirms protection on a second representative v3 route (POST in addition to GET).

Existing tests already cover: health and login public; GET `/api/v3/inventories` missing/invalid/expired token → 401 + envelope; valid token → request passes auth; and that the response is not the default `detail` envelope.

---

## B. Public vs protected route summary

### Public
| Path | Method | Note |
|------|--------|------|
| `/health` | GET | Healthcheck |
| `/auth/login` | POST | Login (no auth required) |

### Protected
| Path | Note |
|------|------|
| `/auth/me` | GET; route-level `Depends(get_current_admin)` |
| `/api/v3/inventories` | GET list, POST create |
| `/api/v3/inventories/{inventory_id}` | GET |
| `/api/v3/inventories/{inventory_id}/metrics` | GET |
| `/api/v3/inventories/{inventory_id}/aisles` | GET list, POST create |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` | POST |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` | GET |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel` | POST |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` | GET |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` | GET list, POST upload |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file` | GET |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` | GET list |
| `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` | GET |
| `/api/v3/inventories/.../positions/{position_id}/reviews` | POST |

**All active v3 business routes** are under the single v3 router and are protected. No v3 operational route is left unprotected.

---

## C. File-by-file modified list

| File | Purpose |
|------|--------|
| `backend/tests/auth/test_route_protection.py` | Added `test_v3_post_inventories_missing_token_unauthorized` to prove POST on a protected v3 route returns 401 with the stable auth envelope when no token is sent. |

No other files were modified. The v3 router, auth routes, server, and auth dependencies were audited and left unchanged.

---

## D. Validation performed

### Tests run
```bash
cd backend && .venv/bin/pytest tests/auth/ -v --no-cov -q
```

### Results
- **16 passed** (6 auth API, 2 auth security, 8 route protection).
- Route protection tests: health public, login public; GET/POST v3 without token → 401 + stable envelope; invalid token → 401; expired token → 401; valid token → passes auth; contract test confirms no `detail`-style auth response.

### Manual verification
- Read `backend/src/api/routes/v3/router.py` in full: single docstring, single import block, single router definition, no duplicates.
- Grep of `include_router` and `APIRouter(` across `backend/src/api`: only one v3 router is mounted (on the app); all v3 routes are under it.
- Confirmed `AuthHttpError` handler in `server.py` returns `to_response_body()` (stable envelope).

---

## E. Scope confirmation

- **No frontend auth work** was added. No login page, token persistence, route guards, or redirect handling.
- **No new auth features** were introduced. Only existing Phase 2 primitives are used (`get_current_admin`, `AuthHttpError`).
- **Phase 3 remained backend route protection only:** one test was added to strengthen proof that the auth boundary is applied to a second HTTP method (POST) on the protected surface. No business logic, DTOs, or router structure was changed beyond the existing Phase 3 implementation.

Phase 3 is clean, correct, and ready to close.
