# Phase 6 — Dead code report

## Method

- Grep for temporary/legacy/compat aliases in critical job paths.
- Vulture not treated as delete authority (dynamic wiring / AppContainer).
- Only remove code when wiring + tests prove unused.

## Findings

| Item | Classification | Action |
| ---- | -------------- | ------ |
| getattr fence on Persist | debt / error | Removed |
| FastAPI in download gate | layering error | Removed |
| Broad `Any` in job_state_consistency | debt | Typed |
| Full SqlJobRepository methods | live | Kept |
| V3JobExecutor CODE_SCAN/OCR paths | live (out of scope) | Kept |
| AppContainer façades | live | Kept |
| Settings getattr in start_aisle_processing | debt | Deferred |
| Frontend/mobile helpers | not audited as blockers | Deferred |

## Deleted in this phase

- No mass dead-code deletion.
- Brief mistaken `application/errors/` package (shadowed `errors.py`) was removed; errors remain in `errors.py`.
