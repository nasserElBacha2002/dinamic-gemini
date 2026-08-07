# Security headers review

## DAST observation

Passive DAST on **localhost HTTP** reported missing:

- Content-Security-Policy
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy

## Where headers already exist (backend API)

`backend/src/api/security_headers.py` → `SecurityHeadersMiddleware` (wired in `server.py`):

| Header | Behavior |
|--------|----------|
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| Referrer-Policy | `strict-origin-when-cross-origin` |
| Permissions-Policy | camera/mic/geo/payment disabled |
| Cross-Origin-Opener-Policy | `same-origin` |
| Strict-Transport-Security | **Only** when hosted runtime + `ENABLE_HSTS` + trusted forwarded hosts — **never on localhost** |
| Content-Security-Policy | Intentionally left to FE hosting (API is JSON) |

Regression: `backend/tests/api/test_phase4_security_hardening.py` asserts `X-Content-Type-Options`.

## Frontend hosting (this remediation)

`frontend/vercel.json` now sets for all routes:

- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- X-Frame-Options: DENY
- CSP (minimal viable for Vite/MUI SPA):
  - `default-src 'self'`
  - `frame-ancestors 'none'`
  - `object-src 'none'`
  - `script-src 'self'`
  - `style-src 'self' 'unsafe-inline'` (required for MUI/Emotion runtime styles)
  - `img-src 'self' data: blob:`
  - `font-src 'self' data:`
  - `connect-src 'self' https: wss:` (API + websockets over TLS)
  - `upgrade-insecure-requests`
  - **no** `unsafe-eval`

## Architecture decision

| Layer | Responsibility |
|-------|----------------|
| FastAPI | API hardening headers (already present) |
| Vercel / FE static host | CSP + browser headers for HTML/JS app |
| Cloudflare / Nginx (if used in prod) | May add/override — avoid contradictory CSP; prefer single CSP owner (FE host) |
| HSTS | Edge or backend gated flag — **not** localhost |

## Why DAST saw gaps on localhost

Likely hitting Vite dev server or a path without production `vercel.json` headers. Dev servers often omit production security headers. Production FE deploy path now declares them.

## Residual

- `style-src 'unsafe-inline'` accepted for Emotion/MUI until a nonce/hash strategy is designed.
- If production uses Cloudflare in front of both API and FE, confirm no duplicate conflicting CSP; prefer FE CSP for documents and API headers for JSON.
