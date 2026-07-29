# Phase 4 — Security architecture review

## Authentication

| Topic | State |
| ----- | ----- |
| JWT algorithm | HS256-only (no `alg=none`) |
| API key | Optional locally; **required** in production/staging/preproduction runtime |
| API key compare | SHA-256 + `secrets.compare_digest` |
| Tokens in query | Not used for auth |
| Token logging | Redacted in observability + mobile logger |

## Authorization / multi-tenant

Phase 2 established `AccessPrincipal` + client scope. Phase 4 revalidated: no new UUID-only admin bypass introduced. Cross-client tests remain in Phase 2 suites — not reopened.

## Uploads / paths

Existing validation (size, path normalization, generated storage keys) retained. No new SSRF URL-fetch sinks found. Path traversal guards on artifacts remain.

## SQL

Bound parameters remain the standard. Bandit B608 on constant f-string SQL with `?` placeholders classified **false positive** (P4-020).

## CORS / headers

| Control | Implementation |
| ------- | -------------- |
| Wildcard + credentials | Rejected at startup via `normalize_cors_allow_origins` |
| Methods/headers | Explicit allowlists (`SAFE_CORS_*`) |
| Security headers | `SecurityHeadersMiddleware` (nosniff, frame deny, referrer, permissions-policy, COOP; optional HSTS) |

## Errors

Unhandled exceptions return stable `INTERNAL_SERVER_ERROR` + generic detail (no stack to client).

## SSRF

No user-controlled webhook/callback URL fetchers identified in Phase 4 inventory. Presigned URLs are generated server-side.

## Frontend / mobile

| Area | State |
| ---- | ----- |
| `dangerouslySetInnerHTML` | Not used |
| VITE secrets | Guarded by test + `.env.example` hygiene |
| Mobile SecureStore | Tokens |
| Mobile TLS | No `verify=False` / TLS disable |

## Rate limiting

No distributed rate limiter introduced (out of Phase 4 critical path). Compensating: upload size/batch limits, authz, job lease fencing (Phase 3), timeouts. Residual risk documented for ops / Phase 5.
