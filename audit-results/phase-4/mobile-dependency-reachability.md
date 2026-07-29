# Phase 4 corrections — Mobile npm Critical/High reachability

Generated from `npm audit --json` + `npm ls` path inspection. Not a blanket “Expo = safe” claim.

## Method

1. `cd mobile && npm audit --json`
2. For each Critical/High advisory, record dependency path via `npm ls <pkg>`
3. Classify environment: `app_runtime` | `dev_cli` | `ci` | `eas_build` | `jest_tooling`

## Summary (Expo 51 lockfile)

| Advisory package | Typical path | Environment | Controllable input? | Mitigation |
| ---------------- | ------------ | ----------- | ------------------- | ---------- |
| `tar` (critical) | `expo` / `@expo/cli` / config plugins | `dev_cli`, `eas_build`, `ci` | Untrusted tarball only if CI/EAS feeds attacker-controlled archives | Exception P4-011; Expo upgrade track |
| `xmldom` / related | Expo config / jest transformers | `dev_cli`, `jest_tooling` | XML from untrusted project config | Same |
| `glob` / `minimatch` lineages | eslint / jest / metro tooling | `ci`, `dev_cli` | Glob patterns from repo config | Same |
| Runtime app deps (expo-secure-store, fetch) | App binary | `app_runtime` | N/A for listed Critical/High tooling CVEs | No Critical/High identified in direct runtime graph for token storage path |

## Conclusion

Critical/High findings in the current Expo 51 audit are **reachable in CI / EAS / developer CLI**, not demonstrated in production app runtime code paths that process untrusted archives. Exception **P4-011** therefore scopes `affected_environments` to `ci`, `eas_build`, `dev_cli` and excludes `app_runtime_production`.

Re-run on Expo major upgrade; do not use `npm audit fix --force`.
