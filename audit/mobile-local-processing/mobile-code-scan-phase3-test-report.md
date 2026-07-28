# Mobile CODE_SCAN Phase 3 — Test Report

## Mobile

| Command | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run test:core` | PASS (147) |
| `npm run test:services -- --testPathPattern=localCodeScanStrategy` | PASS (8) |
| `npm run test:integration` | PASS (8 migrations) |
| `npx expo-doctor` | 16/17 — Xcode 26 vs Expo 51 warning (pre-existing tooling) |

## Android / Gradle

| Command | Result |
| --- | --- |
| `./gradlew :capture-foreground-service:testDebugUnitTest` | BUILD SUCCESSFUL |
| `./gradlew assembleRelease` | BUILD SUCCESSFUL |

## Backend contracts

| Command | Result |
| --- | --- |
| `./venv/bin/pytest backend/tests/application/services/image_processing/test_code_scan_shared_contracts.py` | PASS (9) |

## Release / device

| Scenario | Result |
| --- | --- |
| Samsung S10+ manual matrix (§31) | **NOT EXECUTED** |
| Instrumented Android barcode decode tests | **NOT EXECUTED** (unit stub only) |
| 100-image stress | **NOT EXECUTED** |

## Notes

- Phase 3 unit coverage focuses on parser, consolidator, strategy, flags, migration v8.
- End-to-end ML Kit decode accuracy requires physical corpus — see metrics report (empty measured table).
