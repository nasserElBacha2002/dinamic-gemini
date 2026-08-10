# Phase 6 — Complexity report

## Snapshot (radon / LOC)

| Component | LOC (approx) | Notes |
| --------- | ------------ | ----- |
| `SqlJobRepository` | ~1648 | Mapper + lease predicates extracted; avg complexity still ~B |
| `V3JobExecutor` | ~2154 | High-level orchestrator + large path methods deferred |
| `AppContainer` | ~1750+ | Composition root; provider split deferred |
| `V3JobFinalizationService` | ~790 | Deferred |

## Improvements this phase

- Removed getattr branching in Persist fence path (fewer control-flow surprises).
- Shared lease CAS predicate reduces duplicated SQL branches across fence/complete/fail.
- Characterization tests document fence bool semantics without probing internals of SQL.

## Deferred complexity work

- Split CODE_SCAN/OCR path modules (blocked by Phase 6 “no OCR/CODE_SCAN” rule).
- `SqlJobLeaseStore` / query/command store internal modules.
- AppContainer `*Provider` extraction only when reusable consumers exist.
