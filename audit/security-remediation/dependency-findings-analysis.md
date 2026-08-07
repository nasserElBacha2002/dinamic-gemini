# Dependency findings analysis

**Date:** 2026-08-07  
**Node:** v22.14.0 · **npm:** 11.4.2  
**Scope:** root `package-lock.json`, `frontend/`, `mobile/`

Findings are grouped by **root dependency**, not by every transitive advisory row.

## Summary (npm audit metadata)

| Tree | Before (total) | After (total) | Critical before → after |
|------|----------------|---------------|-------------------------|
| root | 4 | **0** | 1 → 0 |
| frontend | 3 | 2 | 0 → 0 |
| mobile | 32 | 28 | 1 → 0 |

Raw JSON: `audit/security-remediation/npm-audit/*-{before,after}.json`.

## Matrix (root causes)

| finding / advisory theme | package vulnerable | version before | fixed / target | direct/transitive | runtime/build/dev | parent | reachable in product | upgrade required | breaking risk |
|--------------------------|--------------------|----------------|----------------|-------------------|-------------------|--------|----------------------|------------------|---------------|
| Critical shell-quote | shell-quote | <1.8.x via concurrently@8 | 1.9.0 via concurrently@9.2.4 | transitive | **dev** (local `npm run dev`) | concurrently | Not reachable in deployed FE/BE/mobile runtime | Yes (root parent) | Low (dev tooling) |
| High lodash (via concurrently) | lodash | via concurrently@8 | removed with concurrently@9 | transitive | **dev** | concurrently | Not reachable in product runtime | Yes | Low |
| High brace-expansion (root eslint) | brace-expansion | 5.0.5 | 5.0.9 (override) | transitive | **dev** | eslint → minimatch | Dev-only lint tooling | Yes | Low |
| Low @babel/core sourceMappingURL | @babel/core | 7.29.0 | 7.29.7 (override) | transitive | **dev** | eslint-plugin-react-hooks | Dev-only | Yes | Low |
| High js-yaml | js-yaml | <4.3.1 (eslint/expo trees) | 4.3.1 | transitive | frontend: **dev**; mobile: **build** | eslint / @expo/cli | Frontend does not parse external YAML at runtime (uses `yaml` package in devDeps only for tooling). Mobile: Expo config tooling | Yes | Low |
| Moderate/High React Router open redirect / XSS family | react-router / react-router-dom | 6.x (audit-era) | **7.18.2** | direct (frontend) | **runtime** | react-router-dom | Yes (SPA navigation) | Yes | Medium (major 6→7; API mostly compatible for BrowserRouter usage) |
| High RSC CSRF (GHSA-qwww-vcr4-c8h2) | react-router | npm audit range 7.12–8.2 | Official patched: **7.18.2** / 8.3.0 | direct | runtime only if unstable RSC APIs used | react-router-dom | **Not reachable** — Vite SPA, no RSC / Framework Mode actions | Already on 7.18.2 | n/a (npm DB lag) |
| Critical node-tar | tar | vulnerable via @expo/cli → cacache | **7.5.22** (mobile override) | transitive | **build** (Expo CLI), not app runtime | expo@51 → @expo/cli | App does not extract user-controlled TAR archives | Prefer Expo SDK upgrade; temporary override applied | Medium if forcing Expo SDK; override API-compatible for tar |
| Expo tree (@xmldom, postcss, ajv, uuid, fast-xml-parser, send, …) | many | Expo SDK 51 / RN 0.74.5 | Upstream fix needs Expo **≥55/57** per npm audit force path | transitive | mostly **build/dev** | expo, expo-dev-client, react-native CLI | Build-time / tooling; not mobile production JS bundle for most | Planned SDK upgrade (separate) | **High** (SDK major) |

## Reachability notes

- **shell-quote / concurrently:** only root local-dev orchestrator. No production container installs root `node_modules` for API.
- **tar:** introduced by Expo CLI cache/extract paths. No product code imports `tar` for user uploads.
- **React Router:** runtime; mitigated by version bump + `safeInternalPath()` for untrusted hrefs.
- **Mobile residual advisories:** concentrated under Expo CLI / config-plugins / RN CLI; require coordinated SDK upgrade, not one-by-one transitive bumps.

## Do not treat as independent bugs

npm audit lists ~28 mobile “vulnerabilities” after remediation; most are **parent edges** pointing at the same Expo/@xmldom/postcss/fast-xml-parser roots. Count unique root causes, not tree edges.
