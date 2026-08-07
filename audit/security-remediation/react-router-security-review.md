# React Router security review

## Version

| Item | Value |
|------|-------|
| Before | react-router-dom 6.x (audit baseline) |
| After | **react-router-dom@7.18.2** / react-router@7.18.2 |
| Major upgrade | Yes (6 → 7) |
| SSR / Framework Mode / RSC | Not used (Vite SPA + `BrowserRouter`) |

## Advisory handling

1. **Open redirect / XSS family (audit P1):** addressed by upgrading to the npm-recommended patched line (**7.18.2**) and by application-level path sanitization.
2. **GHSA-qwww-vcr4-c8h2 (RSC CSRF):** only affects unstable RSC APIs. This app does not use them. Official patched version on v7 line: **7.18.2** (installed). Residual `npm audit` hit treated as **NOT_REACHABLE** / advisory DB lag.

## Navigation classification

| Class | Meaning | Observed usage |
|-------|---------|----------------|
| A | Internal constant paths / builders (`pathToInventory`, `ROUTE_HOME`, …) | Majority of `navigate()` / `<Link>` |
| B | Paths built from backend IDs | Used via typed helpers (`pathToClient(id)`, etc.) — IDs interpolated into known templates |
| C | Paths from external/query/action hrefs | Analytics action rows, drilldown bars, compare standalone hrefs |

## Mitigation: `safeInternalPath()`

File: `frontend/src/utils/safeInternalPath.ts`  
Tests: `frontend/tests/utils/safeInternalPath.test.ts`

Rules:

- must start with `/`
- reject `//`, backslashes, `http:`, `https:`, `javascript:`, `data:`, scheme-like `/:scheme:`

Applied at untrusted/dynamic link sinks:

- `AnalyticsEntityActionRow`
- `DrilldownActionBar`
- `AnalyticsCompareTab` / `CompareManyRunsWorkspace` standalone navigation

Class A/B navigations continue to use route helpers (already constrained templates).

## RR7 compatibility notes

- Removed obsolete `BrowserRouter` `future` flags (not in RR7 typings; behavior is default).
- Fixed filter-reset race: `handleResetFilters` no longer double-updates via `setSearchDraft('')` + `setSearchParams` (RR7 made the race visible).
- Login test updated so AuthProvider’s post-login `/auth/me` mock succeeds (fail-closed bootstrap).

## Residual risk

Low for open redirect: dynamic hrefs sanitized; library updated. RSC CSRF: not applicable to this architecture.
