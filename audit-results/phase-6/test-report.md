# Phase 6 — Test report

## Characterization / architecture

| Suite | Result |
| ----- | ------ |
| `backend/tests/architecture` (layering + fence characterization) | PASS |
| `backend/tests/observability/test_recover_stale_job.py` | PASS |

## Backend

| Suite | Result |
| ----- | ------ |
| Full `backend/tests` excluding 4 known SQL integration modules | **3997 passed**, 8 skipped |
| Known SQL integration modules (bundle/FK harness) | **8 failed** (pre-existing; Memory evidence / FK `operational_job`) |

## Frontend

| Check | Result |
| ----- | ------ |
| typecheck | PASS |
| lint | PASS (21 warnings, 0 errors) |
| vitest | **1 failed** (timeout: `InventoryAislesSection.pagination` — unrelated to Phase 6; 1222 passed) |

## Mobile

| Check | Result |
| ----- | ------ |
| typecheck | PASS |
| jest unit | 139 passed |
| jest integration | 10 passed |

## Quality

| Check | Result |
| ----- | ------ |
| ruff (touched paths) | PASS |
| `enforce_quality_gate.py --strict` | PASS (uses latest audit snapshot) |

## Phase 7

Not started.
