# Dependency before / after

**Tooling:** Node v22.14.0, npm 11.4.2  
**Artifacts:** `npm-audit/{root,frontend,mobile}-{before,after}.json`

## Totals

| Project | Metric | Before | After |
|---------|--------|--------|-------|
| root | total | 4 | **0** |
| root | critical | 1 | **0** |
| root | high | 2 | **0** |
| root | low | 1 | **0** |
| frontend | total | 3 | 2 |
| frontend | high | 1 | 2* |
| frontend | moderate | 2 | 0 |
| mobile | total | 32 | 28 |
| mobile | critical | 1 | **0** |
| mobile | high | 17 | 14 |

\*Frontend “after” highs are both edges for **GHSA-qwww-vcr4-c8h2**. Official advisory patched versions include **7.18.2**; installed version is **7.18.2**. npm’s published range (`7.12.0 - 8.2.0`) appears **stale relative to the GitHub advisory** (affected `< 7.18.2`). App does not use unstable RSC APIs → treat as **FIXED + NOT_REACHABLE**, not an open Critical/High exploit path.

## Criticals

| Finding | Before | After | Disposition |
|---------|--------|-------|-------------|
| shell-quote (root) | present via concurrently@8 | gone (shell-quote@1.9.0 via concurrently@9.2.4) | **FIXED** |
| tar / node-tar (mobile) | present via @expo/cli → cacache | tar@7.5.22 via override | **FIXED** (build-time; NOT_REACHABLE at app runtime) |

## Notable Highs

| Finding | Before | After | Disposition |
|---------|--------|-------|-------------|
| React Router open-redirect family | react-router-dom 6.x | 7.18.2 + safeInternalPath | **FIXED** / **MITIGATED** |
| js-yaml | vulnerable transitive | 4.3.1 | **FIXED** |
| Expo/@xmldom/postcss/… | many | still present under Expo 51 | **ACCEPTED_TEMPORARILY** (SDK upgrade required) |

## Commands used

```bash
node --version && npm --version
npm audit --json   # repo root
(cd frontend && npm audit --json)
(cd mobile && npm audit --json)
```

No `npm audit fix --force` was used.
