# Dependency upgrade plan

## Applied in this remediation

### Root (P1)

1. `concurrently` **8 → 9.2.4** — clears Critical `shell-quote` and High `lodash` without overrides for those packages.
2. Overrides (documented temporary for lint tree):
   - `brace-expansion` → `^5.0.9`
   - `@babel/core` → `^7.29.7`

### Frontend (P1)

1. `react-router-dom` **6 → 7.18.2** (pulls `react-router@7.18.2`).
2. Override `js-yaml` → `^4.3.1`.
3. Align `brace-expansion` override → `^5.0.9` (5.0.8 was still in advisory range).
4. App hardening: `safeInternalPath()` for dynamic `RouterLink` / navigate targets.

### Mobile (P1 critical + controlled mitigations)

1. **No Expo SDK major in this pass** (Android-native customizations + intentional SDK 51).
2. Temporary overrides (remove after SDK upgrade):
   - `tar` → `^7.5.22` (Critical)
   - `js-yaml` → `^4.3.1`
   - `brace-expansion` → `^2.1.4`
3. Follow-up: Expo SDK upgrade path documented in `mobile-expo-security-upgrade.md`.

## Explicitly rejected

- `npm audit fix --force` (would pull Expo 57 / RN 0.86 / downgrade RR incorrectly).
- Blind one-by-one transitive package.json pins for every Expo advisory.
- Editing lockfiles by hand.

## Temporary overrides policy

| Location | Override | Why temporary | Removal criteria |
|----------|----------|---------------|------------------|
| mobile | tar, js-yaml, brace-expansion | Upstream Expo 51 still resolves vulnerable tar | After SDK upgrade clears advisories without override |
| root | brace-expansion, @babel/core | eslint/babel lag | When direct parents ship fixed ranges |
| frontend | js-yaml, brace-expansion, postcss, minimatch | tooling + prior hardening | Re-evaluate after major FE toolchain bumps |

## Next planned upgrades (out of this PR scope unless unblocked)

1. Expo SDK 51 → supported SDK that clears `@xmldom` / `postcss` / RN CLI advisories (see mobile doc).
2. Re-audit frontend GHSA-qwww after npm advisory DB catches 7.18.2 backport (already installed).
