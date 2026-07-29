# Phase 4 — Security architecture review

## Authentication

| Topic | State |
| ----- | ----- |
| JWT algorithm | HS256-only (no `alg=none`) |
| Public clients (FE/mobile) | **JWT only** (Model A) — no embedded API key |
| API key | Optional; enforced **only** for configured `API_KEY_REQUIRED_PATH_PREFIXES` |
| Health | `/health` and `/ready` never require API key |
| API key compare | SHA-256 + `secrets.compare_digest` |
| Tokens in query | Not used for auth |
| Token logging | Redacted in observability + mobile logger |

## Authorization / multi-tenant

Phase 2 established `AccessPrincipal` + client scope. Phase 4 revalidated: no new UUID-only admin bypass introduced.

## Uploads / paths

Existing validation retained. No new SSRF URL-fetch sinks found.

## SQL TLS

| Environment | Default `TrustServerCertificate` |
| ----------- | -------------------------------- |
| local / test / development | `yes` (configurable) |
| staging / preproduction / production / unknown | `no` |
| Full connection string | Validated (`Encrypt`, trust); hosted insecure trust requires `SQLSERVER_ALLOW_INSECURE_TRUST` |

## SQL injection

Bound parameters remain the standard. Bandit B608 on constant f-string SQL with `?` placeholders classified **false positive** (P4-020).

## CORS / headers

| Control | Implementation |
| ------- | -------------- |
| Hosted origins | Required; HTTPS only; no localhost / wildcard / null |
| Local/test | Localhost defaults allowed |
| Wildcard + credentials | Rejected |
| Methods/headers | Explicit allowlists |
| Security headers | `SecurityHeadersMiddleware` |
| HSTS | Hosted + `ENABLE_HSTS` + trusted forwarded hosts / TLS proxy |

## Errors

Unhandled exceptions return stable `INTERNAL_SERVER_ERROR` + generic detail.

## Frontend / mobile

| Area | State |
| ---- | ----- |
| `dangerouslySetInnerHTML` | Not used |
| VITE secrets | Guarded by test + post-build dist scan |
| Mobile SecureStore | Tokens |
| Mobile Critical/High npm | Documented reachability (`ci`/`eas_build`/`dev_cli`) — P4-011 |

## Rate limiting

No distributed rate limiter (residual). Compensating: upload limits, authz, Phase 3 lease fencing.
