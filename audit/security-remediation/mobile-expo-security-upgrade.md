# Mobile / Expo security upgrade

## Current stack

| Component | Version |
|-----------|---------|
| Expo SDK | **51** (`expo@~51.0.0` → 51.0.39) |
| React Native | **0.74.5** |
| React | 18.2.0 |
| Node (dev machine) | 22.14.0 |
| Project shape | Android-focused; custom native modules under `mobile/modules/` |

## Dependency tree (security-relevant roots)

```
expo@51
├── @expo/cli → tar (CRITICAL before override), js-yaml, @expo/plist → @xmldom/xmldom
├── expo-constants / expo-asset → @expo/config → config-plugins
expo-dev-client → expo-dev-launcher / expo-manifests → ajv, @expo/config
react-native@0.74.5 → @react-native-community/cli → fast-xml-parser, …
```

`npm ls tar js-yaml brace-expansion` after remediation shows **tar@7.5.22**, **js-yaml@4.3.1**, **brace-expansion@2.1.4** via overrides.

## What was done (this pass)

1. **Critical tar — override rolled back.** Forcing `tar@^7.5.22` broke Expo 51 prebuild (`@expo/cli` uses Babel `interopRequireDefault(require('tar'))`; tar v7 sets `__esModule` without a usable `.default`, so `.extract` throws and `android/` is never created). CI symptom: Assemble debug → `mobile/android: No such file or directory`.
2. Cleared **js-yaml** / **brace-expansion** advisories via overrides (kept).
3. **Did not** run `npm audit fix --force` (would jump to Expo 57 / RN 0.86).
4. Validated: `npm run typecheck`, `npm test`, `npm run doctor`; local `CI=1 npx expo prebuild -p android --no-install` after removing tar override.
5. CI workflows updated: drop unsupported `--non-interactive`, set `CI=1`, assert `android/gradlew` exists after prebuild.

## Why not full SDK upgrade now

- Expo doctor reports Xcode 26 vs SDK 51 iOS tooling mismatch; project is **Android-primary** and intentionally stays on SDK 51 until a planned migration.
- Native customizations (`capture-foreground-service`, prebuild android tree) make a blind SDK major high-risk for this remediation window.
- Most residual advisories are **build/dev tooling**, not the production JS runtime parsing untrusted XML/TAR from users.

## Recommended upgrade path (follow-up)

Preference order: patch → minor → SDK.

1. Inventory breaking changes Expo 51 → current LTS/SDK used by the team (npm force suggests **57** as audit’s blunt instrument — treat as upper bound, not mandatory jump).
2. Use Expo upgrade tooling (`npx expo install expo@…` + `npx expo-doctor`) on a dedicated branch.
3. Re-run Android release build (`npm run android:release`) and full mobile tests.
4. Remove `overrides` for tar/js-yaml/brace-expansion when `npm audit` no longer needs them.
5. Re-audit; classify remaining build-only findings.

## Residual classification

| Item | Status |
|------|--------|
| tar critical | **ACCEPTED_TEMPORARILY** / **NOT_REACHABLE** (Expo CLI / cacache build tooling only; tar@7 override incompatible with Expo 51; fix = SDK upgrade that ships tar-7-aware `@expo/cli`) |
| Expo/@xmldom/postcss/ajv/uuid/fast-xml-parser tree | **ACCEPTED_TEMPORARILY** — requires SDK upgrade |
| send (expo cli) | **NOT_REACHABLE** (CLI tooling) |
| Mobile production exploit via these advisories | Not demonstrated; treat as supply-chain/build hygiene |
