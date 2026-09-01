# Mobile offline-first Phase 1 — validation

## Commands

| Command | Result |
|---------|--------|
| `npm run typecheck` (mobile/) | PASS |
| `npm run test:core` | PASS — 316 tests |
| `npm run test:services` | PASS — 225 tests |

## New tests

| Test file | Coverage |
|-----------|----------|
| `catalogRevision.test.ts` | Canonical revision stability + change detection |
| `catalogSyncService.test.ts` | Revision no-op, offline guard, replace failure |
| `catalogColdStart.test.ts` | Offline auth restore, timeout/500 fallback, local inventory list |
| `databaseMigrations.test.ts` | v29 local catalog tables |

## Acceptance criteria mapping

| # | Criterion | Status |
|---|-----------|--------|
| 1 | App opens without Internet | IMPLEMENTED — auth + catalog hydrate from SQLite/SecureStore |
| 2 | No mandatory startup HTTP | IMPLEMENTED — `auth.restore(connectivity)` + local list first |
| 3–5 | SQLite hydrates inventories/suppliers/profiles | IMPLEMENTED — v29 tables + existing recognition tables |
| 6–7 | Recognition resolver after restart | IMPLEMENTED — unchanged resolver; profiles persisted in v28 tables |
| 8–9 | Background sync + reconnect sync | IMPLEMENTED — bootstrap + connectivity subscriber |
| 10–12 | New supplier/inventory/profile after sync | IMPLEMENTED — full catalog fetch + recognition sync per inventory |
| 13 | Draft historical profiles | PARTIAL — via `recognition_profile_snapshot_json` on drafts |
| 14–15 | Atomic sync + rollback | IMPLEMENTED — `replaceCatalogSnapshot` transaction |
| 16–17 | Timeout/500 non-blocking | IMPLEMENTED — tests + service fallbacks |
| 18 | Empty offline UX | IMPLEMENTED — InventoriesScreen message |
| 19 | Operational data preserved | IMPLEMENTED — catalog sync does not touch capture/draft tables |
| 20 | Tests pass | PASS |

## Device test

**NOT EXECUTED** — requires physical device: online sync → kill app → airplane mode → cold start → select inventory/aisle → scan fixture.

Recommended manual checklist:

1. Login online, wait for sync banner timestamp.
2. Force-stop app, enable airplane mode.
3. Open app — inventories visible without spinner blocking.
4. Open golden inventory `eb6f750e-ed12-4c71-b9b2-56a1301e08a8`, aisle `709fe503-2f5c-43ae-b680-25bbc3bbf51f`.
5. Confirm supplier profiles ITEM v10 / POSITION v3 resolve offline.

## Known limitations

- Virgin install with zero sync + offline → empty catalog (by design for Phase 1).
- No `/mobile/catalog` bundle endpoint — uses existing v3 list APIs (multiple calls).
- Profile history for same supplier+kind stored only in draft snapshots (schema PK limit).
